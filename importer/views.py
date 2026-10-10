from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from file_handling.access import (
    CanAccessCountryFiles, validate_uploaded_file, sessions_for, can_delete,
)
from file_handling.models import ImportSession
from file_handling.serializers import ImportSessionSerializer
from .reconciliation.sources import SourceError, is_lock_file
from .services import analysis_service

# Nombre maximal de récaps par import (un export paginé en compte plus de 200) et taille totale d'un envoi
MAX_RECAP_FILES = getattr(settings, 'IMPORT_MAX_RECAP_FILES', 300)
MAX_TOTAL_SIZE = getattr(settings, 'IMPORT_MAX_TOTAL_SIZE', 200 * 1024 * 1024)

ANALYSE_FORBIDDEN_MESSAGE = "Seul l'auteur de cet import (ou l'admin territorial) peut relancer son rapprochement."


def _session_payload(session, request, **extra):
    data = {'session': ImportSessionSerializer(session, context={'request': request}).data}
    data.update(extra)
    return data


def _queued(session, request):
    """Traitement confié au worker (lot I4) : 202, l'interface suit GET /import-sessions/<id>/."""
    return Response(_session_payload(session, request, detail=session.progress_label),
                    status=status.HTTP_202_ACCEPTED)


def _analyse_response(session, request):
    """Réponse après le lancement du rapprochement : 202 s'il tourne en tâche de fond ; s'il est déjà terminé
    (exécution sur place) : 200 si le rapport est produit, 422 si l'analyse s'est arrêtée (mauvais fichier,
    colonne absente, aucune période commune…), avec le motif dans `detail` ; 503 si la file est injoignable."""
    if session.status == ImportSession.Status.PROCESSING:
        return _queued(session, request)
    payload = _session_payload(session, request, detail=session.message)
    if session.status == ImportSession.Status.ANALYSED:
        return Response(payload, status=status.HTTP_200_OK)
    if session.message == analysis_service.QUEUE_UNAVAILABLE:
        return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(payload, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


def _sheet_or_error(session, sheet):
    """(feuilles, message d'erreur ou None) pour la feuille demandée."""
    try:
        sheets = analysis_service.stat_sheets(session)
    except SourceError as exc:
        return [], str(exc)
    if sheet and sheets and sheet not in sheets:
        return sheets, f"La feuille « {sheet} » n'existe pas dans le fichier statistique."
    return sheets, None


class FileUploadAndImportView(APIView):
    """
    Dépôt d'un fichier statistique et d'un ou plusieurs récaps, puis rapprochement (lots I1 et I2).
    Rien n'est écrit dans les tables métier : le résultat est un rapport Excel et des chiffres sur la session.

    Champs : stat_file, recap_files (plusieurs ; recap_file accepté pour un seul), stat_sheet (facultatif).
    Si le fichier statistique a plusieurs feuilles et qu'aucune n'est donnée, la session attend le choix
    de la feuille (statut AWAITING_SHEET, liste dans `sheets`) : POST /import-sessions/<id>/analyse/.
    """
    parser_classes = [MultiPartParser]
    # Admin territorial ou chef de département technique, rattaché à un pays
    permission_classes = [IsAuthenticated, CanAccessCountryFiles]

    def post(self, request, *args, **kwargs):
        # Refus avant lecture du corps
        try:
            content_length = int(request.META.get('CONTENT_LENGTH') or 0)
        except ValueError:
            content_length = 0
        if content_length > MAX_TOTAL_SIZE:
            return Response({'detail': f"Envoi trop volumineux (maximum {MAX_TOTAL_SIZE // (1024 * 1024)} Mo au total)."},
                            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        stat_file = request.FILES.get('stat_file')
        recap_uploads = request.FILES.getlist('recap_files') or request.FILES.getlist('recap_file')
        # Fichiers verrous d'Excel (~$classeur.xlsx) déposés avec un dossier : ignorés
        recap_uploads = [f for f in recap_uploads if not is_lock_file(f.name)]
        sheet = (request.data.get('stat_sheet') or '').strip() or None
        user = request.user
        country = user.country

        if not stat_file or not recap_uploads:
            return Response({'detail': 'Le fichier statistique et au moins un fichier récap sont requis.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(recap_uploads) > MAX_RECAP_FILES:
            return Response({'detail': f"Trop de fichiers récap ({len(recap_uploads)}) : {MAX_RECAP_FILES} au maximum par import."},
                            status=status.HTTP_400_BAD_REQUEST)

        file_errors = [validate_uploaded_file(stat_file, f'Fichier statistique ({stat_file.name})')]
        file_errors += [validate_uploaded_file(f, f'Récap {f.name}') for f in recap_uploads]
        file_errors = [e for e in file_errors if e]
        if file_errors:
            return Response({'detail': ' '.join(file_errors[:5]) + (' …' if len(file_errors) > 5 else ''),
                             'errors': file_errors},
                            status=status.HTTP_400_BAD_REQUEST)

        currency = (request.data.get('currency') or '').strip().upper() or None
        if currency and not (len(currency) == 3 and currency.isalpha()):
            return Response({'detail': 'Devise invalide : code ISO à 3 lettres attendu (ex. XOF).'},
                            status=status.HTTP_400_BAD_REQUEST)

        session = analysis_service.create_session(user, country, stat_file, recap_uploads, currency)
        sheets, error = _sheet_or_error(session, sheet)
        if error:
            analysis_service._fail(session, error)
            return Response(_session_payload(session, request, detail=error, sheets=sheets),
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        if sheet is None and len(sheets) > 1:
            session.status = ImportSession.Status.AWAITING_SHEET
            session.message = "Le fichier statistique contient plusieurs feuilles : choisissez celle à rapprocher."
            session.save(update_fields=['status', 'message'])
            return Response(_session_payload(session, request, detail=session.message, sheets=sheets),
                            status=status.HTTP_200_OK)

        session = analysis_service.queue_analyse(session, sheet or (sheets[0] if sheets else None))
        return _analyse_response(session, request)


class ImportSessionSheetsView(APIView):
    """Feuilles du fichier statistique d'une session (pour choisir ou changer de feuille)."""
    permission_classes = [IsAuthenticated, CanAccessCountryFiles]

    def get(self, request, pk):
        session = get_object_or_404(sessions_for(request.user), pk=pk)
        try:
            sheets = analysis_service.stat_sheets(session)
        except SourceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except FileNotFoundError:
            return Response({'detail': "Le fichier statistique n'est plus disponible sur le serveur."},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'sheets': sheets, 'current': session.stat_sheet})


class ImportSessionAnalyseView(APIView):
    """Rapprochement (ou nouveau rapprochement, sur une autre feuille) d'une session déjà déposée.
    Corps JSON : {"stat_sheet": "<nom de la feuille>"}. Mêmes droits que la suppression de la session."""
    parser_classes = [JSONParser, MultiPartParser]
    permission_classes = [IsAuthenticated, CanAccessCountryFiles]

    ALLOWED = (ImportSession.Status.AWAITING_SHEET, ImportSession.Status.ANALYSED, ImportSession.Status.ERROR)

    def post(self, request, pk):
        session = get_object_or_404(sessions_for(request.user).select_related('stat_file', 'user'), pk=pk)
        if not can_delete(request.user, session):
            return Response({'detail': ANALYSE_FORBIDDEN_MESSAGE}, status=status.HTTP_403_FORBIDDEN)
        if session.status not in self.ALLOWED:
            return Response({'detail': "Cette session ne peut plus être rapprochée."},
                            status=status.HTTP_409_CONFLICT)

        sheet = (request.data.get('stat_sheet') or '').strip() or None
        sheets, error = _sheet_or_error(session, sheet)
        if error:
            return Response({'detail': error, 'sheets': sheets}, status=status.HTTP_400_BAD_REQUEST)
        if sheet is None and len(sheets) > 1:
            return Response({'detail': 'Choisissez la feuille du fichier statistique à rapprocher.', 'sheets': sheets},
                            status=status.HTTP_400_BAD_REQUEST)

        session = analysis_service.queue_analyse(session, sheet or (sheets[0] if sheets else None))
        return _analyse_response(session, request)


class ImportSessionImportView(APIView):
    """Écriture en base des sinistres importables d'une session rapprochée (lot I3).
    Le rapprochement est refait sur les mêmes fichiers et la même feuille ; tout est écrit en une transaction.
    Mêmes droits que la suppression de la session."""
    permission_classes = [IsAuthenticated, CanAccessCountryFiles]

    def post(self, request, pk):
        session = get_object_or_404(sessions_for(request.user).select_related('stat_file', 'user', 'country'), pk=pk)
        if not can_delete(request.user, session):
            return Response({'detail': "Seul l'auteur de cet import (ou l'admin territorial) peut l'écrire en base."},
                            status=status.HTTP_403_FORBIDDEN)
        if session.status != ImportSession.Status.ANALYSED:
            return Response({'detail': "Seule une session rapprochée (et pas encore importée) peut être écrite en base."},
                            status=status.HTTP_409_CONFLICT)
        session = analysis_service.queue_import(session)
        if session.status == ImportSession.Status.PROCESSING:
            return _queued(session, request)
        # Exécution sur place : DONE (200), échec -> session restée ANALYSED avec le motif (500, ou 503 si la file
        # de traitement est injoignable)
        payload = _session_payload(session, request, detail=session.message)
        if session.status == ImportSession.Status.DONE:
            return Response(payload, status=status.HTTP_200_OK)
        if session.message == analysis_service.QUEUE_UNAVAILABLE:
            return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ImportSessionDetailView(APIView):
    """Session d'import (suivi d'un traitement en cours). Un traitement muet depuis trop longtemps est déclaré
    interrompu au passage."""
    permission_classes = [IsAuthenticated, CanAccessCountryFiles]

    def get(self, request, pk):
        session = get_object_or_404(sessions_for(request.user).select_related('user', 'country', 'stat_file',
                                                                              'recap_file'), pk=pk)
        analysis_service.mark_stale(session)
        return Response(ImportSessionSerializer(session, context={'request': request}).data)
