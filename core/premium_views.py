"""
Primes des employeurs (lot I4, décisions du 10/10/2026) : saisie, import de fichier, historique, ratio S/P.
Saisie et import : admin territorial **et** chef de département technique, pour les employeurs de leur pays.
"""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from file_handling.access import validate_uploaded_file
from users.utils import read_import_file
from .family_views import CanManageFamilies
from .models import Claim, Client
from .services import premium_service as prs
from .services.family_service import parse_period

PREMIUM_PERMISSIONS = [IsAuthenticated, CanManageFamilies]


def _error(exc):
    return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class PremiumListView(APIView):
    """GET : employeurs du pays et l'historique de leurs primes ; POST : nouvelle prime
    {client_id, amount, start_date, end_date, note}."""
    permission_classes = PREMIUM_PERMISSIONS
    parser_classes = [JSONParser]

    def get(self, request):
        country = request.user.country
        return Response({'currency': country.currency_code,
                         'results': prs.employers_with_premiums(country, request.query_params.get('search', '').strip())})

    def post(self, request):
        try:
            p = prs.create_premium(request.user.country, request.user, request.data)
        except prs.PremiumError as exc:
            return _error(exc)
        return Response(prs.premium_json(p), status=status.HTTP_201_CREATED)


class PremiumDetailView(APIView):
    permission_classes = PREMIUM_PERMISSIONS
    parser_classes = [JSONParser]

    def patch(self, request, pk):
        try:
            return Response(prs.premium_json(prs.update_premium(request.user.country, request.user, pk, request.data)))
        except prs.PremiumError as exc:
            return _error(exc)

    def delete(self, request, pk):
        try:
            prs.delete_premium(request.user.country, request.user, pk)
        except prs.PremiumError as exc:
            return _error(exc)
        return Response({'detail': 'Prime supprimée.'})


class PremiumHistoryView(APIView):
    permission_classes = PREMIUM_PERMISSIONS

    def get(self, request, client_id):
        return Response(prs.history(request.user.country, client_id))


class PremiumImportView(APIView):
    """Fichier .xlsx / .xls / .csv (champ `file`) ; `dry_run=true` : contrôle sans rien enregistrer."""
    permission_classes = PREMIUM_PERMISSIONS
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'error': 'Choisissez le fichier des primes.'}, status=status.HTTP_400_BAD_REQUEST)
        error = validate_uploaded_file(upload, f'Fichier des primes ({upload.name})')
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        try:
            df = read_import_file(upload)
        except ValueError as exc:
            return Response({'error': f"Fichier illisible : {exc}."}, status=status.HTTP_400_BAD_REQUEST)
        dry_run = str(request.data.get('dry_run', '')).lower() in ('1', 'true', 'oui')
        try:
            return Response(prs.import_premiums(request.user.country, request.user, df, upload.name, dry_run))
        except prs.PremiumError as exc:
            return _error(exc)


class PremiumTemplateView(APIView):
    permission_classes = PREMIUM_PERMISSIONS

    def get(self, request):
        response = HttpResponse(prs.template_bytes(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="modele_import_primes.xlsx"'
        return response


class PremiumSPView(APIView):
    """Ratio S/P par période de prime sur ?start=&end= (obligatoires) ; ?client= pour un employeur, sinon tous ceux
    qui ont une prime sur la période."""
    permission_classes = PREMIUM_PERMISSIONS

    def get(self, request):
        q = request.query_params
        try:
            start, end = parse_period(q.get('start'), q.get('end'))
        except ValueError as exc:
            return _error(exc)
        if not start or not end:
            return Response({'error': 'Indiquez la période analysée (début et fin).'}, status=status.HTTP_400_BAD_REQUEST)
        country = request.user.country
        clients = Client.objects.filter(country=country)
        if q.get('client'):
            clients = clients.filter(pk=q.get('client'))
        else:
            clients = clients.filter(premiums__start_date__lte=end, premiums__end_date__gte=start).distinct()
        clients = list(clients.order_by('name'))
        claims = Claim.objects.filter(country=country)
        return Response({
            'currency': country.currency_code, 'start': start.isoformat(), 'end': end.isoformat(),
            'clients': [prs.client_sp(c, start, end, claims) for c in clients],
            'total': prs.sp_summary([c.id for c in clients], start, end, claims),
        })
