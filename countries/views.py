import pandas as pd
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import status

from . import deactivation
from .models import Country, CountryDeactivationRequest
from .serializers import CountrySerializer, CountryDeactivationRequestSerializer
from users.permissions import IsGlobalAdmin, IsSuperUser
from users.utils import read_import_file

class CreateCountryView(APIView):
    """
    View allowing a superuser or global admin to create a new country.
    It checks for duplicates based on country name and/or code before creation.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()

        if not name or not code:
            return Response(
                {"error": "Les champs 'name' et 'code' sont requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        existing = (Country.objects.filter(name__iexact=name).first()
                    or Country.objects.filter(code__iexact=code).first())
        if existing is not None:
            what = (f"Le pays '{name}' de code '{code}'" if existing.name.lower() == name.lower() and existing.code == code
                    else f"Un pays avec le nom '{name}'" if existing.name.lower() == name.lower()
                    else f"Un pays avec le code '{code}'")
            if not existing.is_active:
                # Un pays « supprimé » est en réalité désactivé : on l'indique et on oriente vers la réactivation
                return Response(
                    {"error": f"{what} existe déjà mais est désactivé ({existing.name}, {existing.code}) : "
                              f"réactivez-le plutôt que de le recréer.",
                     "inactive_country_id": existing.id},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response({"error": f"{what} existe déjà."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CountrySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # nom nettoyé et code en majuscules par le serializer
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CreateCountryFromExcel(APIView):
    """
    View allowing a global admin to bulk create countries from an Excel or CSV file
    (.xlsx, .xls, .csv).
    Required columns: 'name', 'code'.
    Optional columns: 'currency_code', 'currency_name' (defaults: XOF / F CFA).
    Rows are skipped, with their reason, when the name or code is missing or invalid,
    or when a country with the same name or code (case-insensitive) already exists.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = read_import_file(file)
        except Exception as e:
            return Response({'error': f"Fichier invalide : {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # Required columns
        required_headers = ['name', 'code']
        if not all(header in df.columns for header in required_headers):
            return Response({'error': 'Le fichier doit contenir les colonnes : name, code.'}, status=status.HTTP_400_BAD_REQUEST)

        def cell(row, column):
            """Cleaned text of an optional cell, or '' if the column is absent or the cell empty."""
            if column not in df.columns or pd.isna(row[column]):
                return ''
            return str(row[column]).strip()

        created_countries = []
        skipped_rows = []

        for index, row in df.iterrows():
            line = index + 2  # line number in the file (header is line 1)
            name = cell(row, 'name')
            code = cell(row, 'code').upper()

            if not name or not code:
                skipped_rows.append({'row': line, 'reason': "Nom ou code manquant."})
                continue

            existing = Country.objects.filter(name__iexact=name).first()
            label = f"Un pays nommé « {name} »"
            if existing is None:
                existing = Country.objects.filter(code__iexact=code).first()
                label = f"Un pays de code « {code} »"
            if existing is not None:
                inactive = "" if existing.is_active else " mais est désactivé : réactivez-le"
                skipped_rows.append({'row': line, 'reason': f"{label} existe déjà{inactive}."})
                continue

            data = {'name': name, 'code': code}  # nom nettoyé par le serializer
            # Empty currency cells keep the model defaults (XOF / F CFA)
            if cell(row, 'currency_code'):
                data['currency_code'] = cell(row, 'currency_code')
            if cell(row, 'currency_name'):
                data['currency_name'] = cell(row, 'currency_name')

            serializer = CountrySerializer(data=data)
            if not serializer.is_valid():
                reasons = " ".join(str(msg) for errors in serializer.errors.values() for msg in errors)
                skipped_rows.append({'row': line, 'reason': reasons})
                continue
            created_countries.append(serializer.save())

        message = f"{len(created_countries)} pays créé(s) avec succès."
        if skipped_rows:
            message += f" {len(skipped_rows)} ligne(s) ignorée(s)."
        return Response({
            'message': message,
            'created_count': len(created_countries),
            'created_countries': CountrySerializer(created_countries, many=True).data,
            'lignes_ignores': len(skipped_rows),
            'skipped_rows': skipped_rows,
        }, status=status.HTTP_201_CREATED)


class CountryMixin:
    """
    Mixin to provide a method for retrieving a Country instance by pk,
    with optional filtering based on the user's role.
    """

    def get_country(self, pk, user=None):
        try:
            if user and not user.is_superuser_role():
                # Global Admins can only access active countries
                return Country.objects.get(pk=pk, is_active=True)
            return Country.objects.get(pk=pk)
        except Country.DoesNotExist:
            raise NotFound(detail="Pays introuvable.")


class ListCountriesView(APIView):
    """
    View to list countries.
    - Superusers: all countries.
    - Global Admins: active countries by default (lists used to pick a country, e.g. when
      assigning a territorial admin); ?include_inactive=true also returns deactivated
      countries (country management page).
    Each country carries 'pending_deactivation' (id + progress of the pending request, or null).
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def get(self, request):
        user = request.user
        include_inactive = request.query_params.get('include_inactive', '').lower() in ('1', 'true', 'yes')

        countries = Country.objects.all().order_by('name')
        if not user.is_superuser_role() and not include_inactive:
            countries = countries.filter(is_active=True)

        deactivation.expire_overdue()
        pending = {
            r.country_id: r for r in CountryDeactivationRequest.objects
            .filter(status=CountryDeactivationRequest.Status.PENDING).prefetch_related('votes')
        }
        data = CountrySerializer(countries, many=True).data
        for item in data:
            req = pending.get(item['id'])
            item['pending_deactivation'] = None if req is None else {
                'id': req.id,
                'approvals': deactivation.tally(req)[0],
                'required_approvals': req.required_approvals,
            }
        return Response(data, status=status.HTTP_200_OK)


class CountryDetailView(APIView, CountryMixin):
    """
    Retrieve a country's details by its ID, in the same format as the list
    (id, name, code, currency_code, currency_name, is_active).
    - Global Admins: only active countries.
    - Superusers: all countries, active or not.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def get(self, request, pk):
        country = self.get_country(pk, request.user)
        return Response(CountrySerializer(country).data, status=status.HTTP_200_OK)


class CountryUpdateView(APIView, CountryMixin):
    """
    Update a country's information.
    Only allowed for Global Admins and only on active countries.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def put(self, request, pk):
        country = self.get_country(pk, request.user)

        if not country.is_active:
            raise PermissionDenied("Cannot modify an inactive country.")

        serializer = CountrySerializer(country, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CountryDeactivateView(APIView):
    """
    Désactivation d'un pays (jamais de suppression : clients, partenaires et sinistres
    y sont rattachés). Corps : {"reason": "..."} (obligatoire).
    - ADMIN_GLOBAL : crée une demande soumise au quorum des ADMIN_GLOBAL → 201.
    - SUPERUSER    : désactive immédiatement (et clôt une éventuelle demande en cours) → 200.
    Voir countries/deactivation.py pour les règles.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def post(self, request, pk):
        country = Country.objects.filter(pk=pk).first()
        if country is None:
            raise NotFound("Pays introuvable.")
        try:
            req, applied = deactivation.request_or_deactivate(country, request.user, request.data.get('reason'))
        except deactivation.DeactivationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        data = CountryDeactivationRequestSerializer(req, context={'request': request}).data
        if applied:
            data['message'] = f"Le pays {country.name} a été désactivé."
            return Response(data, status=status.HTTP_200_OK)
        data['message'] = (f"Demande de désactivation de {country.name} créée : "
                           f"{data['approvals']}/{req.required_approvals} validation(s). "
                           f"Les autres administrateurs globaux et le SUPERUSER ont été notifiés.")
        return Response(data, status=status.HTTP_201_CREATED)


class CountryReactivateView(APIView):
    """Réactivation d'un pays désactivé (ADMIN_GLOBAL ou SUPERUSER) : lève le gel de ses comptes."""
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def post(self, request, pk):
        country = Country.objects.filter(pk=pk).first()
        if country is None:
            raise NotFound("Pays introuvable.")
        if not deactivation.reactivate(country, request.user):
            return Response({"message": f"Le pays {country.name} est déjà actif."}, status=status.HTTP_200_OK)
        return Response({"message": f"Le pays {country.name} a été réactivé."}, status=status.HTTP_200_OK)


class DeactivationRequestListView(APIView):
    """
    Demandes de désactivation. ?status=PENDING (défaut), APPROVED, REJECTED, EXPIRED,
    CANCELLED ou ALL. ADMIN_GLOBAL et SUPERUSER.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def get(self, request):
        deactivation.expire_overdue()
        wanted = request.query_params.get('status', 'PENDING').upper()
        requests = (CountryDeactivationRequest.objects.select_related('country', 'requested_by', 'decided_by')
                    .prefetch_related('votes__admin'))
        if wanted != 'ALL':
            requests = requests.filter(status=wanted)
        data = CountryDeactivationRequestSerializer(requests, many=True, context={'request': request}).data
        return Response(data, status=status.HTTP_200_OK)


class DeactivationRequestActionView(APIView):
    """
    POST .../<id>/approve/  {"comment": "..."}  → validation (SUPERUSER : désactive)
    POST .../<id>/reject/   {"comment": "..."}  → refus (SUPERUSER : clôt la demande)
    POST .../<id>/cancel/                        → annulation (demandeur ou SUPERUSER)
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]
    action = None  # 'approve' | 'reject' | 'cancel', fixé dans urls.py

    def post(self, request, pk):
        try:
            if self.action == 'cancel':
                req = deactivation.cancel(pk, request.user)
            else:
                req = deactivation.vote(pk, request.user, approve=self.action == 'approve',
                                        comment=request.data.get('comment', ''))
        except deactivation.DeactivationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        req.refresh_from_db()
        data = CountryDeactivationRequestSerializer(req, context={'request': request}).data
        data['message'] = {
            'APPROVED': f"Le pays {req.country.name} a été désactivé.",
            'REJECTED': f"La demande de désactivation de {req.country.name} est refusée.",
            'CANCELLED': f"La demande de désactivation de {req.country.name} est annulée.",
            'PENDING': f"Votre avis est enregistré : {data['approvals']}/{req.required_approvals} validation(s).",
        }.get(req.status, req.get_status_display())
        return Response(data, status=status.HTTP_200_OK)
