import json
import os

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import File
from .serializers import FileSerializer, ImportSessionSerializer
from .access import (
    CanAccessCountryFiles, files_for, sessions_for, session_of_file, can_delete,
    stored_paths, file_paths, remove_paths, DELETE_FORBIDDEN_MESSAGE,
)
from importer.utils.functions import open_excel_csv

# Toutes les vues : AT ou CDT avec un pays, et uniquement les fichiers / sessions de ce pays
# (hors de ce périmètre : 404, comme si l'objet n'existait pas).
FILE_PERMISSIONS = [IsAuthenticated, CanAccessCountryFiles]


def _open_stored(field_file):
    try:
        return field_file.open('rb')
    except (FileNotFoundError, ValueError):
        raise Http404("Le fichier n'est plus disponible sur le serveur.")


def _delete_session(session):
    """Supprime la session entière (fichiers stat + récap, rapport, journal).
    Les données importées restent en base, détachées du fichier (on_delete=SET_NULL)."""
    paths = stored_paths(session)
    stat_file, recap_file = session.stat_file, session.recap_file
    with transaction.atomic():
        session.delete()
        File.objects.filter(pk__in=[stat_file.pk, recap_file.pk]).delete()
        transaction.on_commit(lambda: remove_paths(paths))


class FileListView(APIView):
    permission_classes = FILE_PERMISSIONS

    def get(self, request):
        files = files_for(request.user).select_related('user', 'country').order_by("-uploaded_at")
        serializer = FileSerializer(files, many=True, context={'request': request})
        return Response(serializer.data)


class FileDeleteView(APIView):
    """Supprime la session d'import à laquelle appartient le fichier (les deux fichiers partent ensemble)."""
    permission_classes = FILE_PERMISSIONS

    def delete(self, request, pk):
        file = get_object_or_404(files_for(request.user), pk=pk)
        session = session_of_file(file)
        target = session or file
        if not can_delete(request.user, target):
            return Response({"error": DELETE_FORBIDDEN_MESSAGE}, status=status.HTTP_403_FORBIDDEN)

        if session:
            _delete_session(session)
            return Response({"detail": "Import supprimé (fichier statistique et fichier récap)."},
                            status=status.HTTP_200_OK)

        paths = file_paths(file.file)
        with transaction.atomic():
            file.delete()
            transaction.on_commit(lambda: remove_paths(paths))
        return Response({"detail": "Fichier supprimé."}, status=status.HTTP_200_OK)


class FileDownloadView(APIView):
    permission_classes = FILE_PERMISSIONS

    def get(self, request, pk):
        file = get_object_or_404(files_for(request.user), pk=pk)
        return FileResponse(_open_stored(file.file), as_attachment=True,
                            filename=os.path.basename(file.file.name))


class FilePreviewView(APIView):
    permission_classes = FILE_PERMISSIONS

    def get(self, request, pk):
        file = get_object_or_404(files_for(request.user), pk=pk)
        if not os.path.exists(file.file.path):
            raise Http404("Le fichier n'est plus disponible sur le serveur.")
        try:
            df = open_excel_csv(file.file)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # to_json gère les dates et les NaN, que la réponse JSON ne sait pas sérialiser telles quelles
        first_10_rows = json.loads(df.head(10).to_json(orient='records', date_format='iso', force_ascii=False))

        return Response({
            'preview': first_10_rows,
            'metadata': {
                'total_rows': df.shape[0],
                'total_columns': df.shape[1],
                'preview_row_count': len(first_10_rows)
            }
        }, status=status.HTTP_200_OK)


class ImportSessionListView(APIView):
    permission_classes = FILE_PERMISSIONS

    def get(self, request):
        import_sessions = (
            sessions_for(request.user)
            .select_related('user', 'country', 'stat_file', 'recap_file')
            .order_by("-created_at")
        )
        serializer = ImportSessionSerializer(import_sessions, many=True, context={'request': request})
        return Response(serializer.data)


class ImportSessionDeleteView(APIView):
    permission_classes = FILE_PERMISSIONS

    def delete(self, request, pk):
        session = get_object_or_404(sessions_for(request.user).select_related('stat_file', 'recap_file', 'user'), pk=pk)
        if not can_delete(request.user, session):
            return Response({"error": DELETE_FORBIDDEN_MESSAGE}, status=status.HTTP_403_FORBIDDEN)
        _delete_session(session)
        return Response({"detail": "Import supprimé (fichier statistique et fichier récap)."},
                        status=status.HTTP_200_OK)


class ImportSessionDownloadView(APIView):
    permission_classes = FILE_PERMISSIONS

    def get(self, request, pk):
        session = get_object_or_404(sessions_for(request.user), pk=pk)
        file_type = request.query_params.get('type')

        if file_type == 'error':
            if not session.error_file:
                raise Http404("Aucun rapport d'erreurs pour cette session.")
            return FileResponse(_open_stored(session.error_file), as_attachment=True,
                                filename=os.path.basename(session.error_file.name))

        if file_type == 'log':
            if not session.log_file_path or not os.path.exists(session.log_file_path):
                raise Http404("Aucun journal pour cette session.")
            return FileResponse(open(session.log_file_path, 'rb'), as_attachment=True,
                                filename=os.path.basename(session.log_file_path))

        return Response({"error": "Paramètre 'type' invalide. Utilisez ?type=error ou ?type=log"},
                        status=status.HTTP_400_BAD_REQUEST)
