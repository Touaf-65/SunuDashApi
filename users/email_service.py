"""
Service d'emails optimisé avec envoi asynchrone pour SUNU DASH
"""

import logging
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .email_templates import (
    CREDENTIALS_TEMPLATE, LOGIN_SUCCESS_TEMPLATE, 
    PASSWORD_CHANGE_TEMPLATE, RESET_PASSWORD_TEMPLATE,
    COUNTRY_ASSIGNMENT_TEMPLATE
)

logger = logging.getLogger(__name__)

class EmailService:
    """
    Service d'emails optimisé avec templates personnalisés
    """
    
    @staticmethod
    def send_credentials_email(user, password, role_display):
        """
        Envoie un email avec les identifiants de connexion
        """
        try:
            context = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'username': user.username,
                'password': password,
                'role': role_display,
                'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
                'current_year': datetime.now().year
            }
            
            subject = "Vos identifiants de connexion - SUNU DASH"
            plain_text = f"""
            Bonjour {user.first_name} {user.last_name},
            
            Votre compte SUNU DASH a été créé avec succès.
            
            Email : {user.email}
            Nom d'utilisateur : {user.username}
            Mot de passe : {password}
            Rôle : {role_display}
            
            Connectez-vous à : {context['frontend_url']}/auth/login
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
            
            html_content = CREDENTIALS_TEMPLATE.format(**context)
            
            EmailService._send_email_async(
                to_email=user.email,
                subject=subject,
                plain_text=plain_text,
                html_content=html_content
            )
            
            logger.info(f"Email d'identifiants envoyé à {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email identifiants à {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def send_login_success_email(user, request):
        """
        Envoie un email de confirmation de connexion réussie
        """
        try:
            # Récupérer les informations de connexion
            ip_address = EmailService._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', 'Non disponible')
            
            context = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'login_time': timezone.now().strftime('%d/%m/%Y à %H:%M'),
                'ip_address': ip_address,
                'user_agent': user_agent[:100] + '...' if len(user_agent) > 100 else user_agent,
                'role': user.get_role_display(),
                'dashboard_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app') + '/dashboard',
                'current_year': datetime.now().year
            }
            
            subject = "Connexion Réussie - SUNU DASH"
            plain_text = f"""
            Bonjour {user.first_name} {user.last_name},
            
            Vous êtes maintenant connecté avec succès à votre compte SUNU DASH !
            
            Date et heure : {context['login_time']}
            Adresse IP : {context['ip_address']}
            Rôle : {context['role']}
            
            Accédez à votre tableau de bord : {context['dashboard_url']}
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
            
            html_content = LOGIN_SUCCESS_TEMPLATE.format(**context)
            
            EmailService._send_email_async(
                to_email=user.email,
                subject=subject,
                plain_text=plain_text,
                html_content=html_content
            )
            
            logger.info(f"Email de connexion réussie envoyé à {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email connexion réussie à {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def send_password_change_email(user, request):
        """
        Envoie un email de confirmation de changement de mot de passe
        """
        try:
            ip_address = EmailService._get_client_ip(request)
            
            context = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'changed_at': timezone.now().strftime('%d/%m/%Y à %H:%M'),
                'ip_address': ip_address,
                'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
                'current_year': datetime.now().year
            }
            
            subject = "Mot de passe modifié - SUNU DASH"
            plain_text = f"""
            Bonjour {user.first_name} {user.last_name},
            
            Nous confirmons que votre mot de passe a été modifié avec succès.
            
            Compte : {user.email}
            Date de modification : {context['changed_at']}
            Adresse IP : {context['ip_address']}
            
            Connectez-vous : {context['frontend_url']}/login
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
            
            html_content = PASSWORD_CHANGE_TEMPLATE.format(**context)
            
            EmailService._send_email_async(
                to_email=user.email,
                subject=subject,
                plain_text=plain_text,
                html_content=html_content
            )
            
            logger.info(f"Email de changement de mot de passe envoyé à {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email changement mot de passe à {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def send_reset_password_email(user, otp, expire_at):
        """
        Envoie un email de réinitialisation de mot de passe avec OTP
        """
        try:
            context = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'otp': otp,
                'expire_at': expire_at.strftime('%d/%m/%Y à %H:%M'),
                'current_year': datetime.now().year
            }
            
            subject = "Réinitialisation de mot de passe - SUNU DASH"
            plain_text = f"""
            Bonjour {user.first_name} {user.last_name},
            
            Nous avons reçu une demande de réinitialisation de mot de passe pour votre compte SUNU DASH.
            
            Code de sécurité : {otp}
            Ce code expire le : {context['expire_at']}
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
            
            html_content = RESET_PASSWORD_TEMPLATE.format(**context)
            
            EmailService._send_email_async(
                to_email=user.email,
                subject=subject,
                plain_text=plain_text,
                html_content=html_content
            )
            
            logger.info(f"Email de réinitialisation de mot de passe envoyé à {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email réinitialisation mot de passe à {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def send_country_assignment_email(user, country, assignment_type="assign"):
        """
        Envoie un email d'affectation/réaffectation de pays
        """
        try:
            context = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'country_name': country.name,
                'assignment_date': timezone.now().strftime('%d/%m/%Y à %H:%M'),
                'current_year': datetime.now().year
            }
            
            if assignment_type == "assign":
                subject = "Affectation territoriale - SUNU DASH"
                plain_text = f"""
                Bonjour {user.first_name},
                
                Vous avez été désigné comme Administrateur Territorial pour le pays : {country.name}.
                
                Date d'affectation : {context['assignment_date']}
                Rôle : Administrateur Territorial
                
                SUNU DASH - Votre partenaire d'analyse d'assurance
                """
            elif assignment_type == "reassign":
                subject = "Réaffectation territoriale - SUNU DASH"
                plain_text = f"""
                Bonjour {user.first_name},
                
                Vous avez été réaffecté comme Administrateur Territorial pour le pays : {country.name}.
                
                Date de réaffectation : {context['assignment_date']}
                Rôle : Administrateur Territorial
                
                SUNU DASH - Votre partenaire d'analyse d'assurance
                """
            else:  # unassign
                subject = "Désaffectation territoriale - SUNU DASH"
                plain_text = f"""
                Bonjour {user.first_name},
                
                Vous avez été désaffecté en tant qu'administrateur territorial de votre pays actuel.
                
                Date de désaffectation : {context['assignment_date']}
                
                SUNU DASH - Votre partenaire d'analyse d'assurance
                """
                # Pour la désaffectation, on n'utilise pas le template HTML
                html_content = None
                EmailService._send_email_async(
                    to_email=user.email,
                    subject=subject,
                    plain_text=plain_text,
                    html_content=html_content
                )
                return True
            
            html_content = COUNTRY_ASSIGNMENT_TEMPLATE.format(**context)
            
            EmailService._send_email_async(
                to_email=user.email,
                subject=subject,
                plain_text=plain_text,
                html_content=html_content
            )
            
            logger.info(f"Email d'affectation territoriale envoyé à {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email affectation territoriale à {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def _send_email_async(to_email, subject, plain_text, html_content=None):
        """
        Envoie un email de manière asynchrone (optimisé)
        """
        try:
            # Configuration optimisée pour l'envoi rapide
            send_mail(
                subject=subject,
                message=plain_text,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[to_email],
                fail_silently=False,
                html_message=html_content,
                # Options d'optimisation
                auth_user=settings.EMAIL_HOST_USER,
                auth_password=settings.EMAIL_HOST_PASSWORD,
                connection=None,  # Utilise la connexion par défaut
            )
            
            logger.info(f"Email envoyé avec succès à {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi d'email à {to_email}: {str(e)}")
            raise e
    
    @staticmethod
    def _get_client_ip(request):
        """
        Récupère l'adresse IP du client
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


