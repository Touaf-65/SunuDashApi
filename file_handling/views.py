import imp
from django.shortcuts import render, get_object_or_404
from django.http import FileResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser
from .models import File, ImportSession
from core.models import Claim
from .serializers import FileSerializer, ImportSessionSerializer
from users.permissions import IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry, IsChefDeptTech
from importer.utils.functions import open_excel_csv
import pandas as pd

import os

class FileListView(APIView):
    permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry|IsChefDeptTech]
    
    def get(self, request):
        files = File.objects.filter(country=request.user.country).order_by("-uploaded_at")        
        serializer = FileSerializer(files, many=True)
        return Response(serializer.data)
    

class FileDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry|IsChefDeptTech]
    parser_classes = [JSONParser]

    def delete(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if request.user != file.user and not getattr(request.user, 'is_admin_territorial', False):
            return Response({"detail": "Vous n'avez pas la permission d'effectuer cette action."},status=status.HTTP_403_FORBIDDEN)
        delete_claims = request.data.get('delete_claims', False)

        if delete_claims:
            deleted_count, _ = Claim.objects.filter(file=file).delete()
            msg = f"{deleted_count} sinistres supprimés liés au fichier."
        else:
            Claim.objects.filter(file=file).update(file=None)
            msg = "Référence au fichier retirée des sinistres."

        file.delete()
        return Response({"detail": f"Fichier supprimé avec succès. {msg}"}, status=status.HTTP_204_NO_CONTENT)


class FileDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry|IsChefDeptTech]
    
    def get(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if request.user != file.user and not getattr(request.user, 'is_admin_territorial', False):
            return Response({"detail": "Vous n'avez pas la permission d'effectuer cette action."},status=status.HTTP_403_FORBIDDEN)
        file_path = file.file.path
        return FileResponse(open(file_path, 'rb'), as_attachment=True)
    

class FilePreviewView(APIView):
    permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry|IsChefDeptTech]
    
    def get(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if request.user != file.user and not getattr(request.user, 'is_admin_territorial', False):
            return Response({"detail": "Vous n'avez pas la permission d'effectuer cette action."},status=status.HTTP_403_FORBIDDEN)
        df = open_excel_csv(file.file)
        
        first_10_rows = df.head(10).to_dict(orient='records')

        total_rows = df.shape[0]
        total_columns = df.shape[1]
        
        return Response({
            'preview': first_10_rows,
            'metadata': {
                'total_rows': total_rows,
                'total_columns': total_columns,
                'preview_row_count': len(first_10_rows)
            }
        }, status=status.HTTP_200_OK)


class ImportSessionListView(APIView):
    permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry|IsChefDeptTech]
    
    def get(self, request):
        import_sessions = ImportSession.objects.filter(country=request.user.country).order_by("-created_at")
        serializer = ImportSessionSerializer(import_sessions, many=True, context={'request': request})
        return Response(serializer.data)
    

class ImportSessionDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech]

    def get(self, request, session_id):
        file_type = request.query_params.get('type')

        session = get_object_or_404(ImportSession, id=session_id)

        if session.country != request.user.country:
            return Response({"detail": "Accès interdit à cette session."}, status=status.HTTP_403_FORBIDDEN)

        if file_type == 'error':
            if not session.error_file:
                raise Http404("Aucun fichier d’erreur disponible pour cette session.")
            return FileResponse(session.error_file.open('rb'), as_attachment=True)

        elif file_type == 'log':
            if not session.log_file_path or not os.path.exists(session.log_file_path):
                raise Http404("Aucun fichier de log disponible pour cette session.")
            return FileResponse(open(session.log_file_path, 'rb'), as_attachment=True)

        return Response({"detail": "Paramètre 'type' invalide. Utilisez ?type=error ou ?type=log"},
                        status=status.HTTP_400_BAD_REQUEST)
