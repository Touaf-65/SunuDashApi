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


def _analyse_response(session, request):
    """Réponse après rapprochement : 200 si le rapport est produit, 422 si l'analyse s'est arrêtée
    (mauvais fichier, colonne absente, aucune période commune…), avec le motif dans `detail`."""
    payload = _session_payload(session, request, detail=session.message)
    if session.status == ImportSession.Status.ANALYSED:
        return Response(payload, status=status.HTTP_200_OK)
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

        analysis_service.analyse(session, sheet or (sheets[0] if sheets else None))
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

        analysis_service.analyse(session, sheet or (sheets[0] if sheets else None))
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
        written = analysis_service.import_claims(session)
        payload = _session_payload(session, request, detail=session.message)
        return Response(payload, status=status.HTTP_200_OK if written else status.HTTP_500_INTERNAL_SERVER_ERROR)


import os
import tempfile
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

from users.permissions import IsTerritorialAdmin, IsChefDeptTech, IsGlobalAdmin
from core.services.prime_loader_service import PrimeLoaderService
from core.serializers.prime_import_serializer import (
    PrimeImportRequestSerializer,
    PrimeImportPreviewSerializer,
    PrimeImportResultSerializer,
    PrimeImportStatusSerializer,
    ClientPrimeSerializer,
    ClientPrimeHistorySerializer
)
from core.models import Client, ClientPrimeHistory
from file_handling.models import File, ImportSession


class PrimeImportPreviewView(APIView):
    """
    Vue pour prévisualiser l'import des primes avant exécution
    """
    permission_classes = [IsAuthenticated]  # Temporairement simplifié pour le test
    
    def post(self, request):
        """
        Génère un aperçu de l'import des primes
        
        POST /api/importer/prime-import/preview/
        """
        try:
            # Valider le fichier
            serializer = PrimeImportRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            uploaded_file = serializer.validated_data['file']
            
            # Sauvegarder temporairement le fichier
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                for chunk in uploaded_file.chunks():
                    tmp_file.write(chunk)
                tmp_file_path = tmp_file.name
            
            try:
                # Créer le service de chargement des primes
                prime_service = PrimeLoaderService(request.user)
                
                # Générer l'aperçu
                preview = prime_service.get_import_preview(tmp_file_path)
                
                # Sérialiser la réponse
                preview_serializer = PrimeImportPreviewSerializer(preview)
                
                return Response({
                    'success': True,
                    'message': 'Aperçu généré avec succès',
                    'data': preview_serializer.data
                }, status=status.HTTP_200_OK)
                
            finally:
                # Nettoyer le fichier temporaire
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                    
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Erreur lors de la génération de l\'aperçu: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PrimeImportView(APIView):
    """
    Vue pour importer les primes clients
    """
    permission_classes = [IsAuthenticated]  # Temporairement simplifié pour le test
    
    def post(self, request):
        """
        Importe les primes depuis un fichier Excel
        
        POST /api/importer/prime-import/
        """
        try:
            # Valider le fichier
            serializer = PrimeImportRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            uploaded_file = serializer.validated_data['file']
            
            # Sauvegarder le fichier
            file_path = default_storage.save(
                f'prime_imports/{uploaded_file.name}',
                ContentFile(uploaded_file.read())
            )
            
            # Créer l'enregistrement de fichier
            file_obj = File.objects.create(
                file=file_path,
                user=request.user,
                name=uploaded_file.name,
                file_type='stat'  # Type par défaut pour les imports de primes
            )
            
            try:
                # Créer le service de chargement des primes
                prime_service = PrimeLoaderService(request.user)
                
                # Importer les primes (sans session d'import pour le moment)
                result = prime_service.import_primes(
                    default_storage.path(file_path),
                    None  # Pas de session d'import pour le test
                )
                
                # Gérer le cas où il n'y a pas de session d'import
                import_session = None
                
                # Sérialiser la réponse
                result_serializer = PrimeImportResultSerializer(result)
                
                return Response({
                    'success': True,
                    'message': f'Import terminé. {result["imported_count"]} primes importées.',
                    'data': result_serializer.data
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                # Gérer l'erreur sans session d'import
                pass
                
                return Response({
                    'success': False,
                    'message': f'Erreur lors de l\'import: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Erreur lors du traitement: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PrimeImportStatusView(APIView):
    """
    Vue pour vérifier le statut d'un import de primes
    """
    permission_classes = [IsAuthenticated]  # Temporairement simplifié pour le test
    
    def get(self, request, import_session_id):
        """
        Récupère le statut d'un import de primes
        
        GET /api/importer/prime-import/status/{import_session_id}/
        """
        try:
            # Récupérer la session d'import
            import_session = ImportSession.objects.get(id=import_session_id)
            
            # Sérialiser la réponse
            status_serializer = PrimeImportStatusSerializer(import_session)
            
            return Response({
                'success': True,
                'data': status_serializer.data
            }, status=status.HTTP_200_OK)
            
        except ImportSession.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session d\'import non trouvée'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Erreur lors de la récupération du statut: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientPrimeListView(APIView):
    """
    Vue pour lister les primes des clients
    """
    permission_classes = [IsAuthenticated]  # Temporairement simplifié pour le test
    
    def get(self, request):
        """
        Liste les primes des clients du pays de l'utilisateur
        
        GET /api/importer/prime-import/clients/
        """
        try:
            # Créer le service pour récupérer le pays de l'utilisateur
            prime_service = PrimeLoaderService(request.user)
            
            # Récupérer les clients selon le type d'utilisateur
            if prime_service.user_country is None:
                # Admin global : tous les clients
                clients = Client.objects.all().order_by('name')
            else:
                # Autres utilisateurs : clients de leur pays
                clients = Client.objects.filter(
                    country=prime_service.user_country
                ).order_by('name')
            
            # Sérialiser la réponse
            client_serializer = ClientPrimeSerializer(clients, many=True)
            
            return Response({
                'success': True,
                'data': client_serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Erreur lors de la récupération des clients: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientPrimeHistoryView(APIView):
    """
    Vue pour l'historique des primes d'un client
    """
    permission_classes = [IsAuthenticated]  # Temporairement simplifié pour le test
    
    def get(self, request, client_id):
        """
        Récupère l'historique des primes d'un client
        
        GET /api/importer/prime-import/clients/{client_id}/history/
        """
        try:
            # Créer le service pour récupérer le pays de l'utilisateur
            prime_service = PrimeLoaderService(request.user)
            
            # Récupérer le client selon le type d'utilisateur
            if prime_service.user_country is None:
                # Admin global : peut accéder à tous les clients
                client = Client.objects.get(id=client_id)
            else:
                # Autres utilisateurs : seulement les clients de leur pays
                client = Client.objects.get(
                    id=client_id,
                    country=prime_service.user_country
                )
            
            # Récupérer l'historique des primes
            prime_history = client.prime_history.all().order_by('-date')
            
            # Sérialiser la réponse
            history_serializer = ClientPrimeHistorySerializer(prime_history, many=True)
            
            return Response({
                'success': True,
                'client_name': client.name,
                'current_prime': client.prime,
                'data': history_serializer.data
            }, status=status.HTTP_200_OK)
            
        except Client.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Client non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Erreur lors de la récupération de l\'historique: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# class UploadAndValidateFiles(APIView):
#     permission_classes = [IsAuthenticated, IsTerritorialAdminAndAssignedCountry|IsTerritorialAdmin]

#     expected_stat_headers = [
#         "Nom Employeur", "Broker Name", "Nom bénéficiaire", "Acte_Contraté_Assuré",
#         "Statut Assuré", "Numero de police", "Nom Assuré Principal", "Nom du partenaire",
#         "Adresse du Partenaire", "Pays du partenaire", "Numero de sinistre", "Statut",
#         "Date de sinistre", "Date de règlement", "Categorie d'acte", "Famille Acte",
#         "Nom Acte", "Montant facturé", "N°cheque/Autre_Moyent_de_payement",
#         "Note Générale", "Numero de Facture", "Modifié par"
#     ]

#     expected_recap_headers = [
#         "reglementId", "date_reglement", "beneficiaire", "N°_Cheque",
#         "autres_Moyen_de_payement", "partnerId", "Assurés_principal", "Employeur",
#         "N°_police", "totalmttreclame", "totalmttrembourse", "NumFacture", "Note"
#     ]

#     def post(self, request):
#         file_stat = request.FILES.get('file_stat')
#         file_recap = request.FILES.get('file_recap')

#         if not file_stat or not file_recap:
#             return Response({"error": "Les deux fichiers doivent être fournis."}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             df_stat = open_excel_csv(file_stat)
#             df_recap = open_excel_csv(file_recap)

#             missing_stat = [h for h in self.expected_stat_headers if h not in df_stat.columns]
#             missing_recap = [h for h in self.expected_recap_headers if h not in df_recap.columns]

#             if missing_stat or missing_recap:
#                 return Response({
#                     "errors": {
#                         "stat_file_missing": missing_stat,
#                         "recap_file_missing": missing_recap
#                     }
#                 }, status=status.HTTP_400_BAD_REQUEST)
            
#             # print(f"stat columns: {df_stat.columns}")
#             # print(f"recap columns: {df_recap.columns}")

#             df_stat_clean = CleaningService().clean_stat_dataframe(df_stat)

#             # print(f'###VIEWS### df_stat_clean columns: {df_stat_clean.columns}')

#             df_recap_clean = CleaningService().clean_recap_dataframe(df_recap)

#             common_range = ComparisonService().get_common_date(df_stat_clean, df_recap_clean)


#             if common_range is None:
#                 return Response({
#                     "error": "Les fichiers ne couvrent pas de période commune."
#                 }, status=status.HTTP_400_BAD_REQUEST)

#             print(f'###VIEWS### common_range: {common_range}')
            
#             df_recap_clean = ComparisonService().rename_recap_columns(df_recap_clean)
#             df_comparison = ComparisonService().compare_dataframes(df_stat_clean, df_recap_clean, common_range)

#             # print(f'###VIEWS### df_comparison columns: {df_comparison.columns}')

#             # print(f'###VIEWS### df_comparison: {df_comparison}')

#             df_non_conformes, df_conformes = ComparisonService().extract_non_conformity(df_comparison)
            
#             # print(f'###VIEWS### df_conformes columns: {df_conformes.columns}')

#             print(f'###VIEWS### df_non_conformes: {df_non_conformes}')

#             # print(f'###VIEWS### df_non_conformes columns: {df_non_conformes}')

#             if df_conformes.empty and df_non_conformes.empty:
#                 return Response({
#                     "warning": "Aucune donnée exploitable dans la période commune. Les deux fichiers sont invalides."
#                 }, status=status.HTTP_204_NO_CONTENT)

#             if df_conformes.empty:
#                 print(f"# views: df conforme vide")
#                 file_path = generate_no_conformity_excel(df_non_conformes, df_stat, df_recap)
#                 return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))

#             file_instance1 = File.objects.create(
#                 file=file_stat,
#                 file_type='stat',
#                 user=request.user,
#                 country=request.user.country,
#             )

#             file_instance2 = File.objects.create(
#                 file=file_recap,
#                 file_type='recap',
#                 user=request.user,
#                 country=request.user.country,
#             )

#             nb_insured, nb_claimes, total_claimed, total_reimbursed, errors =importer_data(df_conformes, request.user, file_instance1)

#             if df_non_conformes.empty:
#                 return Response({
#                     "message": "Les deux fichiers sont conformes.",
#                     "date_range": {
#                         "start": str(common_range[0]),
#                         "end": str(common_range[1])
#                     }, 
#                     "imported_count": {
#                         "insured": nb_insured,
#                         "claims": nb_claimes,
#                         "total_claimed": total_claimed,
#                         "total_reimbursed": total_reimbursed,
#                     }
#                 }, status=status.HTTP_201_CREATED)

#             # Générer le fichier de non-conformité
#             file_path = generate_no_conformity_excel(df_non_conformes, df_stat, df_recap)
#             return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))
#             # return Response({"message": "Fichiers valides."}, status=status.HTTP_201_CREATED)
#         except Exception as e:
#             print("Traceback de l'erreur :")
#             print(traceback.format_exc())  
#             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            