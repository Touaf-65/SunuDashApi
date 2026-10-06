from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import CustomUser, PasswordResetToken
from countries.models import Country
from .serializers import UserSerializer, PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from countries.serializers import CountrySerializer
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Q
from django.contrib.auth.models import User

from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from rest_framework_simplejwt.tokens import RefreshToken
from .permissions import IsSuperUser, IsGlobalAdmin, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry, HasAccessCountry 
import re
import random
import string
import os
import logging
import pandas as pd
from django.db import transaction

from django.contrib.auth import get_user_model

from .utils import generate_password, send_user_email
from .email_service import EmailService
from .tasks import (
    send_credentials_email_task, 
    send_country_assignment_email_task,
    send_reset_password_email_task
)

logger = logging.getLogger(__name__)


class CredentialsEmailError(Exception):
    """The credentials email of a newly created account could not be sent."""


class SuperuserCreateAPIView(APIView):
    """
    API to create the first superuser.
    Endpoint only accessible if no superuser exists.
    """

    def post(self, request):
        # Check if a superuser already exists
        if CustomUser.objects.filter(is_superuser=True).exists():
            return Response({'detail': 'Le superutilisateur existe déjà.'}, status=status.HTTP_403_FORBIDDEN)

        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email']
        for field in required_fields:
            if not request.data.get(field):
                return Response({'detail': f'Le champ {field} est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')

        # Validate email format
        try:
            validate_email(email)
        except ValidationError:
            return Response({'detail': 'Adresse email invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate a random password
        password = generate_password()

        # Create the superuser and send its credentials atomically: the password is only
        # ever transmitted by email, so the account must not exist if the email fails.
        try:
            with transaction.atomic():
                user = CustomUser.objects.create_superuser(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                    is_staff=True,
                    is_superuser=True,
                    role=CustomUser.Roles.SUPERUSER,
                )
                # EmailService catches SMTP errors itself and returns False
                if not EmailService.send_credentials_email(user, password, "Superutilisateur"):
                    raise CredentialsEmailError()
        except CredentialsEmailError:
            return Response(
                {'detail': "Le compte n'a pas été créé : l'e-mail d'identifiants n'a pas pu être envoyé. Réessayez plus tard."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Superutilisateur créé avec succès. Identifiants envoyés par email.'}, status=status.HTTP_201_CREATED)


class LoginUserAPIView(APIView):
    """
    API endpoint for user login via username or email.
    """

    # Route publique : ignorer tout en-tête Authorization (un jeton absent ou expiré
    # envoyé par le navigateur ne doit pas provoquer de 401).
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        login = request.data.get('login')
        password = request.data.get('password')

        if not (login and password):
            return Response({'error': 'Login (nom d’utilisateur ou e-mail) et mot de passe sont requis.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=login, password=password)

        if user is not None:
            if not user.is_active:
                return Response({"error": "Votre compte a été désactivé. Veuillez contacter un administrateur."},
                                status=status.HTTP_403_FORBIDDEN)

            # Envoyer un email de confirmation de connexion (en arrière-plan)
            try:
                EmailService.send_login_success_email(user, request)
            except Exception as e:
                # Ne pas bloquer la connexion si l'email échoue
                pass

            refresh = RefreshToken.for_user(user)
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'username': user.username,
                'email': user.email,
                'role': user.role,
            }, status=status.HTTP_200_OK)

        return Response({"error": "Identifiants invalides."}, status=status.HTTP_401_UNAUTHORIZED)


class GetConnectedUserByLogin(APIView):
    """
    API endpoint to retrieve user information based on username or email.

    URL parameter:
        - login: The username or email of the user.

    Only the connected user's own profile can be read (the sign-in page calls it
    right after login with the login just typed).

    Response:
        - 200 OK: Returns the connected user's information.
        - 401 Unauthorized: Not authenticated.
        - 404 Not Found: The login does not match the connected user (whether or not
          another account exists, so accounts cannot be enumerated).
        - 500 Internal Server Error: For unexpected errors.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, login):
        try:
            user = CustomUser.objects.filter(
                Q(username__iexact=login) | Q(email__iexact=login)
            ).select_related('country').first()

            if not user or user.pk != request.user.pk:
                return Response({'error': 'Utilisateur non trouvé.'}, status=status.HTTP_404_NOT_FOUND)

            data = {
                'id': user.id,
                'role': user.role,
                'country': {
                    'id': user.country.id,
                    'name': user.country.name
                } if user.country else None,
                'email': user.email,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': 'Une erreur est survenue.', 'details': str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyPassword(APIView):
    """
    API endpoint to verify if the provided password matches the authenticated user's password.

    Method: POST
    Request body:
        {
            "password": "user_password"
        }

    Returns:
        - 200 OK with True if the password is correct.
        - 401 Unauthorized with False if the password is incorrect.
        - 400 Bad Request if password is missing.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        password = request.data.get('password')

        if not password:
            return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if user.check_password(password):
            return Response(True, status=status.HTTP_200_OK)
        else:
            return Response(False, status=status.HTTP_401_UNAUTHORIZED)


class PasswordResetRequestView(APIView):
    """
    API endpoint to handle password reset requests.
    
    This endpoint generates a unique reset token and sends a password reset link
    to the user's email address. The token expires after 24 hours.
    
    Method: POST
    Request body:
        {
            "email": "user@example.com"
        }
    
    Returns:
        - 200 OK: Reset email sent successfully
        - 400 Bad Request: Invalid email format or user not found
        - 500 Internal Server Error: Email sending failed
    """

    # Route publique : ignorer tout en-tête Authorization (un jeton absent ou expiré
    # envoyé par le navigateur ne doit pas provoquer de 401).
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                return Response({"error": "Aucun utilisateur trouvé avec cet email."}, status=status.HTTP_404_NOT_FOUND)

            # Supprimer les anciens tokens du même utilisateur
            PasswordResetToken.objects.filter(user=user).delete()

            # Créer un nouveau token
            token = PasswordResetToken.objects.create(user=user)

            # Lien de réinitialisation
            reset_link = f"{settings.FRONTEND_URL}/auth/new-password/{token.token}/"

            from_email = settings.EMAIL_HOST_USER

            subject = 'Demande de réinitialisation de votre mot de passe Sunu Dash'

            plain_message=(
                f"Bonjour {user.first_name},\n\n"
                f"Pour réinitialiser votre mot de passe, cliquez sur ce lien :\n"
                f"{reset_link}\n"
                f"Ce lien expirera dans 24h."
                )

            html_message = f"""
                <html>
                <body style='font-family: Arial, sans-serif; background: #f8f9fa; padding: 32px;'>
                    <div style='max-width: 480px; margin: auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 32px;'>
                        <h2 style='color: #2d5be3; margin-bottom: 12px;'>Réinitialisation de votre mot de passe</h2>
                        <p style='font-size: 16px; color: #222;'>Bonjour <strong>{user.first_name}</strong>,</p>                            <p style='font-size: 16px; color: #222;'>Vous avez demandé la réinitialisation de votre mot de passe Sunu Dash.</p>
                        <p style='font-size: 16px; color: #222;'>Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe&nbsp;:</p>
                        <div style='margin: 24px 0;'>
                            <a href='{reset_link}' style='background: #2d5be3; color: #fff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 16px;'>Réinitialiser mon mot de passe</a>
                        </div>
                        <p style='font-size: 14px; color: #555;'>Ce lien expirera dans 24 heures.</p>
                        <hr style='margin: 28px 0;'>
                        <p style='font-size: 13px; color: #999;'>Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.<br>Ceci est un message automatique. Merci de ne pas répondre directement à cet email.</p>                        
                    </div>
                </body>
                </html>
            """

            # Envoi de l'e-mail
            try:
                send_user_email(
                    to_email=email,
                    subject=subject,
                    plain_text_content=plain_message,
                    html_content=html_message
                )
                return Response({"message": "Un email de réinitialisation de mot de passe a été envoyé."}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({'detail': f"Échec de l'envoi de l'email : {str(e)}"}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    """
    API endpoint to confirm password reset using a valid token.
    
    This endpoint allows users to set a new password using the token received
    via email. The token is automatically deleted after successful password reset.
    
    Method: POST
    Request body:
        {
            "token": "uuid-token",
            "new_password": "new_password",
            "confirm_password": "new_password"
        }
    
    Returns:
        - 200 OK: Password reset successful
        - 400 Bad Request: Invalid token, expired token, or password mismatch
    """

    # Route publique : ignorer tout en-tête Authorization (un jeton absent ou expiré
    # envoyé par le navigateur ne doit pas provoquer de 401).
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            from_email = settings.EMAIL_HOST_USER

            try:
                reset_token = PasswordResetToken.objects.get(token=token)
                if reset_token.is_expired():
                    return Response({"error": "Le lien de réinitialisation a expiré."}, status=status.HTTP_400_BAD_REQUEST)
            except PasswordResetToken.DoesNotExist:
                return Response({"error": "Lien de réinitialisation invalide."}, status=status.HTTP_400_BAD_REQUEST)

            # Changement du mot de passe
            user = reset_token.user
            user.set_password(new_password)
            user.save()

            # Suppression du token après utilisation
            reset_token.delete()

            # E-mail de confirmation (sans le mot de passe). Le mot de passe est déjà changé :
            # un échec d'envoi ne doit pas faire échouer la requête (EmailService renvoie False).
            EmailService.send_password_change_email(user, request)

            return Response({"message": "Votre mot de passe a été réinitialisé avec succès."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateGlobalAdminView(APIView):
    """
    API view that allows a superuser to create a new Global Administrator.

    Method: POST
    Required fields: first_name, last_name, email

    Responses:
        - 201 Created: Admin successfully created and credentials emailed
        - 400 Bad Request: Missing or invalid fields
        - 409 Conflict: A user with this email already exists
        - 503 Service Unavailable: Credentials email could not be sent (account not created)
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')

        if not (first_name and last_name and email):
            return Response({'error': 'Champs requis manquants.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate email format
        try:
            validate_email(email)
        except ValidationError:
            return Response({'error': 'Adresse e-mail invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check for existing user
        if CustomUser.objects.filter(email=email).exists():
            return Response({'error': "Un utilisateur avec cet e-mail existe déjà."}, status=status.HTTP_409_CONFLICT)

        password = generate_password(length=8)

        # Create the account and send its credentials atomically: if the email cannot be
        # sent, the account is rolled back so no one ends up unable to log in.
        try:
            with transaction.atomic():
                user = CustomUser.objects.create_user(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                    is_staff=True,
                    role=CustomUser.Roles.ADMIN_GLOBAL,
                )
                # EmailService catches SMTP errors itself and returns False
                if not EmailService.send_credentials_email(user, password, "Administrateur Global"):
                    raise CredentialsEmailError()
        except CredentialsEmailError:
            return Response(
                {'error': "Le compte n'a pas été créé : l'e-mail d'identifiants n'a pas pu être envoyé. Réessayez plus tard."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response({'error': f"Échec de la création de l'utilisateur : {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


        return Response(
            {"message": "Administrateur Global créé avec succès. Un email contenant les informations de connexion a été envoyé."},
            status=status.HTTP_201_CREATED
        )


class CreateAdminGlobalFromFileView(APIView):
    """
    API endpoint to create Global Administrators from an uploaded Excel file.

    The uploaded file must contain at least the following columns:
    - first_name
    - last_name
    - email

    If a 'role' column exists, only users whose role value is a variant of
    'Administrateur Global' (case-insensitive, tolerant to '-', '_', accents, and spaces)
    will be created.

    Existing users (by email) or invalid emails are skipped.
    Passwords are randomly generated and emailed to users upon successful creation.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "Aucun fichier fourni."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception:
            return Response({"detail": "Fichier Excel invalide."}, status=status.HTTP_400_BAD_REQUEST)

        required_columns = ['first_name', 'last_name', 'email']
        if not all(col in df.columns for col in required_columns):
            return Response({
                "detail": "Le fichier doit contenir les colonnes suivantes : first_name, last_name, email."
            }, status=status.HTTP_400_BAD_REQUEST)

        ignored_count = 0
        created_count = 0
        failed_emails = []

        # Role filtering
        if 'role' in df.columns:
            def normalize_role(role):
                return re.sub(r'[^a-z]', '', str(role).lower())

            df['role_cleaned'] = df['role'].apply(normalize_role)
            valid_roles = {'adminglobal', 'administrateurglobal', 'adminglob', 'administrateurglob'}
            df = df[df['role_cleaned'].isin(valid_roles)]

        for _, row in df.iterrows():
            email = str(row['email']).strip()
            first_name = str(row['first_name']).strip()
            last_name = str(row['last_name']).strip()

            # Validate email
            try:
                validate_email(email)
            except ValidationError:
                ignored_count += 1
                continue

            # Skip rows without first or last name (empty Excel cells are read as NaN)
            if pd.isna(row['first_name']) or pd.isna(row['last_name']) or not first_name or not last_name:
                ignored_count += 1
                continue

            # Skip existing users
            if CustomUser.objects.filter(email=email).exists():
                ignored_count += 1
                continue

            # Create user and send credentials atomically: if the email fails, the account
            # is rolled back so no one ends up with an account they cannot log into.
            password = generate_password(length=8)
            try:
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        password=password,
                        is_staff=True,
                        is_active=True,
                        role=CustomUser.Roles.ADMIN_GLOBAL,
                    )
                    self._send_credentials_email(user, password)
            except Exception as e:
                logger.warning("Import admin global : compte non créé pour %s (échec envoi e-mail : %s)", email, e)
                failed_emails.append(email)
                continue

            created_count += 1


        message = f"{created_count} administrateur(s) global(aux) créé(s) avec succès."
        if failed_emails:
            message += (f" {len(failed_emails)} compte(s) non créé(s) car l'e-mail d'identifiants "
                        f"n'a pas pu être envoyé : {', '.join(failed_emails)}.")
        return Response(
            {
                "message": message,
                "created_count": created_count,
                "lignes_ignores": ignored_count,
                "echecs_envoi_email": failed_emails,
            },
            status=status.HTTP_200_OK
        )

    @staticmethod
    def _send_credentials_email(user, password):
            subject = 'Votre compte Administrateur Global sur SUNU DASH a été créé'
            plain_message = (
                f"Bonjour {user.first_name},\n\n"
                f"Votre nom d'utilisateur est : {user.username}\n"
                f"Votre mot de passe est : {password}\n"
                f"Votre rôle sur la plateforme est : Administrateur Global.\n\n"
                f"Merci de changer votre mot de passe après votre première connexion."
            )
            html_message = f"""
                <html>
                <body style='font-family: Arial, sans-serif; background: #f8f9fa; padding: 32px;'>
                    <div style='max-width: 480px; margin: auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 32px;'>
                        <h2 style='color: #2d5be3; margin-bottom: 12px;'>Bienvenue sur Sunu Dash !</h2>
                        <p style='font-size: 16px; color: #222;'>Bonjour <strong>{user.first_name}</strong>,</p>
                        <p style='font-size: 16px; color: #222;'>Votre compte <b>Administrateur Global</b> a été créé avec succès. Voici vos identifiants&nbsp;:</p>
                        <ul style='font-size: 16px; color: #222; list-style: none; padding: 0;'>
                            <li><b>Nom d'utilisateur&nbsp;:</b> <span style='color: #2d5be3;'>{user.username}</span></li>
                            <li><b>Mot de passe&nbsp;:</b> <span style='color: #2d5be3;'>{password}</span></li>
                            <li><b>Rôle&nbsp;:</b> <span style='color: #2d5be3;'>Administrateur Global</span></li>
                        </ul>
                        <p style='font-size: 15px; color: #444; margin-top: 20px;'>Merci de changer votre mot de passe après votre première connexion pour garantir la sécurité de votre compte.</p>
                        <hr style='margin: 28px 0;'>
                        <p style='font-size: 13px; color: #999;'>Ceci est un message automatique. Merci de ne pas répondre directement à cet email.</p>
                    </div>
                </body>
                </html>
            """
            send_user_email(
                to_email=user.email,
                subject=subject,
                plain_text_content=plain_message,
                html_content=html_message
            )


class GlobalAdminListView(APIView):
    """
    API endpoint to retrieve all global administrators.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get(self, request):
        users = CustomUser.objects.filter(role=CustomUser.Roles.ADMIN_GLOBAL).order_by('-date_joined')
        if not users.exists():
            return Response({'detail': 'Aucun administrateur global trouvé.'}, status=status.HTTP_204_NO_CONTENT)

        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GlobalAdminMixin:
    """
    Utility mixin to retrieve a global administrator by primary key.
    """
    def get_global_admin(self, pk):
        try:
            return CustomUser.objects.get(pk=pk, role=CustomUser.Roles.ADMIN_GLOBAL)
        except CustomUser.DoesNotExist:
            return None


class GlobalAdminDetailView(APIView, GlobalAdminMixin):
    """
    API endpoint to retrieve details of a global administrator.
    Accessible only by superusers.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get(self, request, pk):
        user = self.get_global_admin(pk)
        if not user:
            return Response({'error': 'Administrateur global non trouvé'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GlobalAdminUpdateView(APIView, GlobalAdminMixin):
    """
    API endpoint to update a global administrator.
    Accessible only by superusers.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def put(self, request, pk):
        user = self.get_global_admin(pk)
        if not user:
            return Response({'error': 'Administrateur global non trouvé'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GlobalAdminDeleteView(APIView, GlobalAdminMixin):
    """
    API endpoint to delete a global administrator.
    Accessible only by superusers.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def delete(self, request, pk):
        user = self.get_global_admin(pk)
        if not user:
            return Response({'error': 'Administrateur global non trouvé'}, status=status.HTTP_404_NOT_FOUND)

        user.delete()
        return Response({'detail': 'Administrateur global supprimé avec succès.'}, status=status.HTTP_204_NO_CONTENT)


class CreateTerritorialAdminView(APIView):
    """
    View to create a new Territorial Admin (ADMIN_TERRITORIAL).
    
    Only Global Admins (ADMIN_GLOBAL) is authorized to access this endpoint.
    The user is created with a randomly generated password, marked as staff,
    and receives an email with their login credentials.
    
    """

    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.user.is_admin_global():
            first_name = request.data.get('first_name')
            last_name = request.data.get('last_name')
            email = request.data.get('email')
            from_email = settings.EMAIL_HOST_USER

            if not (first_name and last_name and email):
                return Response({'error': 'Champs manquants requis'}, status=status.HTTP_400_BAD_REQUEST)

            password = generate_password(length=8)

            # Create the account and send its credentials atomically: if the email cannot be
            # sent, the account is rolled back so no one ends up unable to log in.
            try:
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        password=password,
                        is_staff=True,
                        role=CustomUser.Roles.ADMIN_TERRITORIAL,
                    )
                    try:
                        self._send_credentials_email(user, password)
                    except Exception as e:
                        raise CredentialsEmailError() from e
            except CredentialsEmailError as e:
                logger.warning("Création admin territorial : compte non créé pour %s (échec envoi e-mail : %s)", email, e.__cause__)
                return Response(
                    {'error': "Le compte n'a pas été créé : l'e-mail d'identifiants n'a pas pu être envoyé. Réessayez plus tard."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


            return Response({'detail': 'Administrateur Territorial créé avec succès. Identifiants envoyés par email.'}, status=status.HTTP_201_CREATED)

        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    @staticmethod
    def _send_credentials_email(user, password):
            subject =  'Votre nouveau compte Administrateur Territorial sur SUNU DASH a été créé'

            plain_text = f"""
            Bonjour {user.first_name},

            Votre nom d'utilisateur est : {user.username}
            Votre mot de passe est : {password}
            Votre rôle sur la plateforme est : Administrateur Territorial.

            Merci de changer votre mot de passe après votre première connexion pour garantir la sécurité de votre compte.
            """

            html_message=f"""
                <html>
                <body style='font-family: Arial, sans-serif; background: #f8f9fa; padding: 32px;'>
                    <div style='max-width: 480px; margin: auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 32px;'>
                        <h2 style='color: #2d5be3; margin-bottom: 12px;'>Bienvenue sur Sunu Dash !</h2>
                        <p style='font-size: 16px; color: #222;'>Bonjour <strong>{user.first_name}</strong>,</p>
                        <p style='font-size: 16px; color: #222;'>Votre compte <b>Administrateur Territorial</b> a été créé avec succès. Voici vos identifiants&nbsp;:</p>
                        <ul style='font-size: 16px; color: #222; list-style: none; padding: 0;'>
                            <li><b>Nom d'utilisateur&nbsp;:</b> <span style='color: #2d5be3;'>{user.username}</span></li>
                            <li><b>Mot de passe&nbsp;:</b> <span style='color: #2d5be3;'>{password}</span></li>
                            <li><b>Rôle&nbsp;:</b> <span style='color: #2d5be3;'>Administrateur Territorial</span></li>                            
                        </ul>
                        <p style='font-size: 15px; color: #444; margin-top: 20px;'>Merci de changer votre mot de passe après votre première connexion pour garantir la sécurité de votre compte.</p>
                        <hr style='margin: 28px 0;'>
                        <p style='font-size: 13px; color: #999;'>Ceci est un message automatique. Merci de ne pas répondre directement à cet email.</p>
                    </div>
                </body>
                </html>
            """
            send_user_email(
                to_email=user.email,
                subject=subject,
                plain_text_content=plain_text,
                html_content=html_message
            )


class CreateTerritorialAdminsFromExcel(APIView):
    """
    API view allowing superusers or global admins to bulk create territorial admins
    from an uploaded Excel file. Each row must contain: firstname, lastname, and email.
    Emails must be unique. Credentials are saved to a text file and sent by email.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        required_headers = ['firstname', 'lastname', 'email']
        if not all(header in df.columns for header in required_headers):
            return Response({'error': 'Missing required headers in the Excel file'}, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        ignored_count = 0
        failed_emails = []

        for _, row in df.iterrows():
            first_name = str(row['firstname']).strip()
            last_name = str(row['lastname']).strip()
            email = str(row['email']).strip().lower()

            # Skip invalid emails and rows without first or last name (empty cells are read as NaN)
            try:
                validate_email(email)
            except ValidationError:
                ignored_count += 1
                continue
            if pd.isna(row['firstname']) or pd.isna(row['lastname']) or not first_name or not last_name:
                ignored_count += 1
                continue

            if CustomUser.objects.filter(email=email).exists():
                ignored_count += 1
                continue

            # Create user and send credentials atomically: if the email fails, the account
            # is rolled back so no one ends up with an account they cannot log into.
            password = generate_password(length=8)
            try:
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        password=password,
                        is_staff=True,
                        role=CustomUser.Roles.ADMIN_TERRITORIAL,
                    )
                    CreateTerritorialAdminView._send_credentials_email(user, password)
            except Exception as e:
                logger.warning("Import admin territorial : compte non créé pour %s (échec envoi e-mail : %s)", email, e)
                failed_emails.append(email)
                continue

            created_count += 1


        message = f"{created_count} administrateur(s) territorial(aux) créé(s) avec succès."
        if failed_emails:
            message += (f" {len(failed_emails)} compte(s) non créé(s) car l'e-mail d'identifiants "
                        f"n'a pas pu être envoyé : {', '.join(failed_emails)}.")
        return Response(
            {
                'message': message,
                'created_count': created_count,
                'lignes_ignores': ignored_count,
                'echecs_envoi_email': failed_emails,
            },
            status=status.HTTP_201_CREATED
        )


class TerritorialAdminListView(APIView):
    """
    API view to retrieve all territorial admins.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def get(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        territorial_admins = CustomUser.objects.filter(role=CustomUser.Roles.ADMIN_TERRITORIAL)
        serializer = UserSerializer(territorial_admins, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TerritorialAdminMixin:
    """
    Utility mixin to retrieve a territorial administrator by primary key.
    
    This mixin provides a common method to get territorial admin objects
    and handle the case where the admin doesn't exist. It ensures the user
    has the correct ADMIN_TERRITORIAL role.
    """
    def get_object(self, pk):
        try:
            return CustomUser.objects.get(pk=pk, role=CustomUser.Roles.ADMIN_TERRITORIAL)
        except CustomUser.DoesNotExist:
            return None


class TerritorialAdminDetailView(APIView, TerritorialAdminMixin):
    """
    API endpoint to retrieve details of a territorial administrator.
    
    This endpoint allows global admins to view the complete information
    of a territorial administrator including their assigned country.
    
    Method: GET
    URL parameter: pk (user ID)
    
    Returns:
        - 200 OK: Territorial admin details
        - 404 Not Found: If admin doesn't exist
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def get(self, request, pk):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        admin = self.get_object(pk)
        if not admin:
            return Response({"error": "Territorial admin not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(admin)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TerritorialAdminUpdateView(APIView, TerritorialAdminMixin):
    """
    API endpoint to update a territorial administrator's information.
    
    This endpoint allows global admins to modify territorial admin details.
    Partial updates are supported - only provided fields will be updated.
    
    Method: PUT
    URL parameter: pk (user ID)
    
    Returns:
        - 200 OK: Updated territorial admin details
        - 400 Bad Request: Invalid data
        - 404 Not Found: If admin doesn't exist
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def put(self, request, pk):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        admin = self.get_object(pk)
        if not admin:
            return Response({"error": "Territorial admin not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(admin, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TerritorialAdminDeleteView(APIView, TerritorialAdminMixin):
    """
    API endpoint to delete a territorial administrator.
    
    This endpoint performs a hard delete of the territorial admin user.
    The operation is irreversible and will remove all associated data.
    
    Method: DELETE
    URL parameter: pk (user ID)
    
    Returns:
        - 204 No Content: Admin successfully deleted
        - 404 Not Found: If admin doesn't exist
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def delete(self, request, pk):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        admin = self.get_object(pk)
        if not admin:
            return Response({"error": "Territorial admin not found."}, status=status.HTTP_404_NOT_FOUND)

        admin.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssignCountryToTerritorialAdminView(APIView):
    """
    Assign a country to a territorial admin.

    Only global admins can assign a country to a user 
    with the role of ADMIN_TERRITORIAL. An email notification is sent 
    to the admin upon successful assignment.

   Returns:
        200 OK on success,
        404 if user or country not found,
        400 if request data is invalid.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        email = request.data.get("email")
        country_id = request.data.get("country_id")

        if not email or not country_id:
            return Response({"error": "L'email et le pays sont requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin = CustomUser.objects.get(email=email, role=CustomUser.Roles.ADMIN_TERRITORIAL)
        except CustomUser.DoesNotExist:
            return Response({"error": "Administrateur territorial introuvable."}, status=status.HTTP_404_NOT_FOUND)

        try:
            country = Country.objects.get(id=country_id)
        except Country.DoesNotExist:
            return Response({"error": "Pays introuvable."}, status=status.HTTP_404_NOT_FOUND)

        admin.country = country
        admin.save()

        # Send assignment email
        subject = "Affectation territoriale sur SUNU DASH"

        plain_text = (
            f"Bonjour {admin.first_name},\n\n"
            f"Vous avez été affecté au pays : {country.name}."
            )

        html_message = f"""
            <html>
            <body style='font-family: Arial, sans-serif; padding: 32px; background-color: #f9f9f9;'>
                <div style='max-width: 480px; margin: auto; background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);'>
                    <h2 style='color: #2d5be3;'>Nouvelle affectation</h2>
                    <p>Bonjour <strong>{admin.first_name}</strong>,</p>
                    <p>Vous avez été désigné comme <strong>Administrateur Territorial</strong> pour le pays : <strong style='color:#2d5be3;'>{country.name}</strong>.</p>
                    <p>Connectez-vous à votre tableau de bord pour accéder à vos nouvelles responsabilités.</p>
                    <hr>
                    <p style='font-size: 13px; color: #888;'>Ceci est un message automatique de Sunu Dash.</p>
                </div>
            </body>
            </html>
        """

        try:
                send_user_email(
                    to_email=email,
                    subject=subject,
                    plain_text_content=plain_text,
                    html_content=html_message
                )
        except Exception as e:
            return Response({
                "message": f"{admin.email} assigné à {country.name}, mais l'email n'a pas pu être envoyé : {str(e)}"
            }, status=status.HTTP_200_OK)

        return Response({"message": f"{admin.email} assigné au pays {country.name} avec succès."}, status=status.HTTP_200_OK)


class UnassignOrReassignCountryView(APIView):
    """
    Unassign or reassign a country for a territorial admin.

    Superusers or global admins can remove the assigned country 
    from a territorial admin (set to None) or assign a new one.

    An email notification is sent to the admin in both cases.

    Returns:
        200 OK on success,
        404 if user or country not found,
        400 if request data is invalid or redundant.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        email = request.data.get("email")
        country_id = request.data.get("country_id")

        if not email:
            return Response({"error": "L'email est requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin = CustomUser.objects.get(email=email, role=CustomUser.Roles.ADMIN_TERRITORIAL)
        except CustomUser.DoesNotExist:
            return Response({"error": "Administrateur territorial introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if country_id is None:
            # Unassign
            admin.country = None
            admin.save()

            subject = "Désaffectation territoriale sur SUNU DASH"
            plain_text = f"Bonjour {admin.first_name},\n\nVous avez été désaffecté de votre pays dans SUNU DASH."

            html_message = f"""
            <html>
            <body style='font-family: Arial, sans-serif; padding: 32px; background-color: #f9f9f9;'>
                <div style='max-width: 480px; margin: auto; background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);'>
                    <h2 style='color: #e33c3c;'>Désaffectation</h2>
                    <p>Bonjour <strong>{admin.first_name}</strong>,</p>
                    <p>Vous avez été désaffecté en tant qu'administrateur territorial de votre pays actuel.</p>
                    <hr>
                    <p style='font-size: 13px; color: #888;'>Ceci est un message automatique de Sunu Dash.</p>
                </div>
            </body>
            </html>
            """
            try:
                send_user_email(admin.email, subject, plain_text, html_message)
            except Exception as e:
                return Response({
                    "message": f"{admin.email} désassigné, mais l'email n'a pas pu être envoyé : {str(e)}"
                }, status=status.HTTP_200_OK)

            return Response({"message": f"{admin.email} désassigné de tout pays avec succès."}, status=status.HTTP_200_OK)

        else:
            try:
                country = Country.objects.get(id=country_id)
            except Country.DoesNotExist:
                return Response({"error": "Pays introuvable."}, status=status.HTTP_404_NOT_FOUND)

            if admin.country == country:
                return Response({"error": f"{admin.email} est déjà assigné à ce pays."}, status=status.HTTP_400_BAD_REQUEST)

            admin.country = country
            admin.save()

            subject = "Réaffectation territoriale sur SUNU DASH"
            plain_text = f"Bonjour {admin.first_name},\n\nVous avez été réaffecté au pays : {country.name}."

            html_message = f"""
            <html>
            <body style='font-family: Arial, sans-serif; padding: 32px; background-color: #f9f9f9;'>
                <div style='max-width: 480px; margin: auto; background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);'>
                    <h2 style='color: #2d5be3;'>Réaffectation</h2>
                    <p>Bonjour <strong>{admin.first_name}</strong>,</p>
                    <p>Vous avez été réaffecté en tant qu'administrateur territorial pour le pays : 
                    <strong style='color:#2d5be3;'>{country.name}</strong>.</p>
                    <hr>
                    <p style='font-size: 13px; color: #888;'>Ceci est un message automatique de Sunu Dash.</p>
                </div>
            </body>
            </html>
            """
            try:
                # Utiliser le service d'emails optimisé
                EmailService.send_country_assignment_email(admin, country, "reassign")
            except Exception as e:
                return Response({
                    "message": f"{admin.email} réassigné à {country.name}, mais l'email n'a pas pu être envoyé : {str(e)}"
                }, status=status.HTTP_200_OK)

            return Response({"message": f"{admin.email} réassigné au pays {country.name} avec succès."}, status=status.HTTP_200_OK)


class CreateUserByTerritorialAdmin(APIView):
    """
    API view allowing a Territorial Admin to create users (either Technical Department Head
    or Data Entry Manager) within their assigned country. The email must be unique and the
    created user will inherit the Territorial Admin's country.
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry]

    def post(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')
        role = request.data.get('role', CustomUser.Roles.RESP_OPERATEUR)  # Default role
        from_email = settings.EMAIL_HOST_USER

        allowed_roles = ['CHEF_DEPT_TECH', 'RESP_OPERATEUR']
        role_labels = {
            'CHEF_DEPT_TECH': 'Chef Département Technique',
            'RESP_OPERATEUR': 'Responsable Opérateur de Saisie'
        }

        if role not in allowed_roles:
            return Response(
                {"error": "Rôle non autorisé pour un admin territorial."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not all([first_name, last_name, email]):
            return Response(
                {"error": "Les champs prénom, nom et email sont requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if CustomUser.objects.filter(email=email).exists():
            return Response(
                {"error": "Un utilisateur avec cet email existe déjà."},
                status=status.HTTP_400_BAD_REQUEST
            )

        password = generate_password(length=8)

        # Create the account and send its credentials atomically: if the email cannot be
        # sent, the account is rolled back so no one ends up unable to log in.
        try:
            with transaction.atomic():
                user = CustomUser.objects.create_user(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                    country=request.user.country,
                    role=role
                )
                # EmailService catches SMTP errors itself and returns False
                if not EmailService.send_credentials_email(user, password, role_labels.get(role, 'Utilisateur')):
                    raise CredentialsEmailError()
        except CredentialsEmailError:
            return Response(
                {'error': "Le compte n'a pas été créé : l'e-mail d'identifiants n'a pas pu être envoyé. Réessayez plus tard."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CreateUsersByTerritorialAdminFromExcel(APIView):
    """
    Allows a Territorial Admin to bulk create users within their country from an Excel file.
    The Excel file must contain the following headers: firstname, lastname, email, role.
    Roles must be in a recognizable form; common variants are supported.

    Existing users (based on email) are ignored. Only new users are created and emailed.
    Returns the number of users successfully created.
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry]

    def post(self, request):
        if not request.user.is_active:
            return Response(
                {"erreur": "Votre compte est désactivé. Veuillez contacter votre administrateur."},
                status=status.HTTP_403_FORBIDDEN
            )

        file = request.FILES.get('file')
        if not file:
            return Response({'erreur': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception as e:
            return Response({'erreur': f'Fichier Excel invalide : {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        required_headers = ['firstname', 'lastname', 'email', 'role']
        if not all(header in df.columns for header in required_headers):
            return Response({'erreur': 'Le fichier Excel doit contenir les colonnes : firstname, lastname, email, role.'}, status=status.HTTP_400_BAD_REQUEST)

        # Role mapping
        import unicodedata

        def normalize_role(val):
            if not isinstance(val, str):
                return ''
            val = unicodedata.normalize('NFD', val.strip().lower())
            return ''.join(c for c in val if unicodedata.category(c) != 'Mn').replace(' ', '').replace('_', '')

        role_variants = {
            'CHEF_DEPT_TECH': ['chefdepartementtechnique', 'chefdepttech', 'chefdepartement', 'chefdept', 'cheftechnique', 'chef', 'cdt'],
            'RESP_OPERATEUR': ['responsableoperateur', 'responsableoperateurdesaisie', 'responsableops', 'respoperateur', 'respops', 'ops', 'responsable', 'ro']
        }

        role_labels = {
            'CHEF_DEPT_TECH': 'Chef Département Technique',
            'RESP_OPERATEUR': 'Responsable Opérateur de Saisie'
        }

        def map_role(val):
            norm = normalize_role(val)
            for key, variants in role_variants.items():
                if norm in variants:
                    return key
            return None

        created_count = 0
        ignored_count = 0
        failed_emails = []

        for _, row in df.iterrows():
            first_name = str(row['firstname']).strip()
            last_name = str(row['lastname']).strip()
            email = str(row['email']).strip().lower()
            raw_role = row['role']

            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                ignored_count += 1
                continue  # skip invalid email

            # Skip rows without first or last name (empty cells are read as NaN)
            if pd.isna(row['firstname']) or pd.isna(row['lastname']) or not first_name or not last_name:
                ignored_count += 1
                continue

            if CustomUser.objects.filter(email=email).exists():
                ignored_count += 1
                continue  # skip existing user

            role = map_role(raw_role)
            if not role:
                ignored_count += 1
                continue  # skip unknown role

            # Create user and send credentials atomically: if the email fails, the account
            # is rolled back so no one ends up with an account they cannot log into.
            password = generate_password(length=8)
            try:
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        password=password,
                        country=request.user.country,
                        role=role
                    )
                    self._send_credentials_email(user, password, role_labels.get(role, role))
            except Exception as e:
                logger.warning("Import utilisateurs : compte non créé pour %s (échec envoi e-mail : %s)", email, e)
                failed_emails.append(email)
                continue

            created_count += 1

        message = f"{created_count} utilisateur(s) créé(s) avec succès."
        if failed_emails:
            message += (f" {len(failed_emails)} compte(s) non créé(s) car l'e-mail d'identifiants "
                        f"n'a pas pu être envoyé : {', '.join(failed_emails)}.")
        return Response({
            'message': message,
            'created_count': created_count,
            'lignes_ignores': ignored_count,
            'echecs_envoi_email': failed_emails,
        }, status=status.HTTP_201_CREATED)

    @staticmethod
    def _send_credentials_email(user, password, role_label):
        send_mail(
            subject=f'Votre compte {role_label} sur Sunu Dash',
            message=f"""
                Bonjour {user.first_name},

                Votre compte a été créé sur la plateforme Sunu Dash.

                Nom d'utilisateur : {user.username}
                Mot de passe : {password}
                Rôle : {role_label}

                Merci de modifier votre mot de passe lors de votre première connexion.
            """,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
            html_message=f"""
                <html>
                <body style='font-family: Arial, sans-serif; background: #f8f9fa; padding: 32px;'>
                    <div style='max-width: 480px; margin: auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 32px;'>
                        <h2 style='color: #2d5be3;'>Bienvenue sur Sunu Dash !</h2>
                        <p>Bonjour <strong>{user.first_name}</strong>,</p>
                        <p>Votre compte <b>{role_label}</b> a été créé avec succès. Voici vos identifiants :</p>
                        <ul>
                            <li><b>Nom d'utilisateur :</b> {user.username}</li>
                            <li><b>Mot de passe :</b> {password}</li>
                            <li><b>Rôle :</b> {role_label}</li>
                        </ul>
                        <p>Merci de modifier votre mot de passe après votre première connexion.</p>
                    </div>
                </body>
                </html>
            """
        )




class SimpleUserListView(APIView):
    """
    Returns the list of non-admin users for a given country.
    - Superusers and Global Admins see all users (except superusers and admins).
    - Territorial Admins only see users in their own assigned country.
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry]

    def get(self, request):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        user = request.user
        allowed_roles = [
            CustomUser.Roles.CHEF_DEPT_TECH,
            CustomUser.Roles.RESP_OPERATEUR
        ]

        users = CustomUser.objects.filter(
            role__in=allowed_roles,
            country=user.country
        )

        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SimpleUserMixin:
    """
    Utility mixin to retrieve a simple user by primary key.
    
    This mixin provides a common method to get simple user objects and ensures
    the user belongs to the same country as the requesting territorial admin.
    It excludes superusers and admin users from the query results.
    """

    def get_object(self, pk):
        try:
            return CustomUser.objects.get(
                pk=pk,
                role__in=[
                    CustomUser.Roles.CHEF_DEPT_TECH,
                    CustomUser.Roles.RESP_OPERATEUR
                ],
                country=self.request.user.country
            )
        except CustomUser.DoesNotExist:
            return None


class SimpleUserDetailView(APIView, SimpleUserMixin):
    """
    API view to retrieve the details of a simple user (Department Head or Operations Manager)
    restricted to the country of the currently authenticated Territorial Admin.
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry]

    def get(self, request, pk):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        user = self.get_object(pk)
        if not user:
            return Response({"error": "Utilisateur non trouvé."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SimpleUserUpdateView(APIView, SimpleUserMixin):
    """
    API view to update a simple user's data (Department Head or Operations Manager),
    limited to the same country as the requesting Territorial Admin.
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry]

    def put(self, request, pk):

        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )

        user = self.get_object(pk)
        if not user:
            return Response({"error": "Utilisateur non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        # Un admin territorial peut passer un utilisateur de son pays d'un rôle simple à l'autre
        serializer = UserSerializer(
            user, data=request.data, partial=True,
            context={'assignable_roles': (CustomUser.Roles.CHEF_DEPT_TECH, CustomUser.Roles.RESP_OPERATEUR)},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SimpleUserDeleteView(APIView, SimpleUserMixin):
    """
    API view to delete a simple user (Department Head or Operations Manager),
    only if the user belongs to the same country as the Territorial Admin making the request.
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry]

    def delete(self, request, pk):
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        user = self.get_object(pk)
        if not user:
            return Response({"error": "Utilisateur non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ToggleUserActiveView(APIView):
    """
    API view to toggle the active status of a user.

    Permissions:
    - Superusers can activate/deactivate global admins.
    - Global admins can activate/deactivate territorial admins.
    - Territorial admins can activate/deactivate simple users within their assigned country.

    The endpoint expects the user ID (pk) in the URL and toggles the is_active field.
    Returns a success message indicating the new status.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        current_user = request.user

        try:
            target_user = CustomUser.objects.get(pk=pk)
        except CustomUser.DoesNotExist:
            return Response({"error": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if current_user.is_superuser:
            if target_user.role != CustomUser.Roles.ADMIN_GLOBAL:
                return Response({"error": "Vous ne pouvez activer/désactiver que des admins globaux."}, status=status.HTTP_403_FORBIDDEN)
        
        elif current_user.role == CustomUser.Roles.ADMIN_GLOBAL:
            if target_user.role != CustomUser.Roles.ADMIN_TERRITORIAL:
                return Response({"error": "Vous ne pouvez activer/désactiver que des admins territoriaux."}, status=status.HTTP_403_FORBIDDEN)
        
        elif current_user.role == CustomUser.Roles.ADMIN_TERRITORIAL:
            if target_user.country != current_user.country:
                return Response({"error": "Cet utilisateur n'appartient pas à votre pays."}, status=status.HTTP_403_FORBIDDEN)
            if target_user.role in [CustomUser.Roles.ADMIN_GLOBAL, CustomUser.Roles.ADMIN_TERRITORIAL]:
                return Response({"error": "Vous ne pouvez pas activer/désactiver cet utilisateur."}, status=status.HTTP_403_FORBIDDEN)
        
        else:
            return Response({"error": "Vous n'avez pas la permission d'effectuer cette action."}, status=status.HTTP_403_FORBIDDEN)

        target_user.is_active = not target_user.is_active
        target_user.save()

        status_text = "activé" if target_user.is_active else "désactivé"
        return Response({"message": f"L'utilisateur {target_user.email} a été {status_text}."}, status=status.HTTP_200_OK)
