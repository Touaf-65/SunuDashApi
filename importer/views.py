import traceback
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse
from rest_framework import status
from django.core.exceptions import ValidationError
from users.permissions import IsTerritorialAdmin,IsTerritorialAdminAndAssignedCountry, IsChefDeptTech
from .services.importer_service import ImporterService
from .services.comparison_service import ComparisonService
from .services.cleaning_service import CleaningService
# from .services.data_mapper import importer_data
from django.core.files.uploadedfile import UploadedFile
from file_handling.models import File

from .utils.functions import *

class FileUploadAndImportView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech]

    expected_stat_headers = [
        "Nom Employeur", "Broker Name", "Nom bénéficiaire", "Acte_Contraté_Assuré",
        "Statut Assuré", "Numero de police", "Nom Assuré Principal", "Nom du partenaire",
        "Adresse du Partenaire", "Pays du partenaire", "Numero de sinistre", "Statut",
        "Date de sinistre", "Date de règlement", "Categorie d'acte", "Famille Acte",
        "Nom Acte", "Montant facturé", "N°cheque/Autre_Moyent_de_payement",
        "Note Générale", "Numero de Facture", "Modifié par"
    ]

    expected_recap_headers = [
        "reglementId", "date_reglement", "beneficiaire", "N°_Cheque",
        "autres_Moyen_de_payement", "partnerId", "Assurés_principal", "Employeur",
        "N°_police", "totalmttreclame", "totalmttrembourse", "NumFacture", "Note"
    ]

    def post(self, request, *args, **kwargs):
        stat_file = request.FILES.get('stat_file')
        recap_file = request.FILES.get('recap_file')
        user = request.user
        country = getattr(user, 'country', None)  


        if not stat_file or not recap_file:
            return Response({'detail': 'Les deux fichiers (stat et recap) sont requis.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not country:
            return Response({'detail': 'Utilisateur sans pays associé.'},
                            status=status.HTTP_400_BAD_REQUEST)


        try:
            df_stat = open_excel_csv(stat_file)
            df_recap = open_excel_csv(recap_file)

            missing_stat = [h for h in self.expected_stat_headers if h not in df_stat.columns]
            missing_recap = [h for h in self.expected_recap_headers if h not in df_recap.columns]

            if missing_stat or missing_recap:
                return Response({
                    "errors": {
                        "stat_file_missing": missing_stat,
                        "recap_file_missing": missing_recap
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'detail': 'Une erreur est survenue : ' + str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        try:
            importer = ImporterService(
                user=user,
                country=country,
                stat_file=stat_file,
                recap_file=recap_file
            )
            print("##VIEWS: ImporterService instancié")
            success = importer.run()

            if success:
                return Response({'detail': 'Import lancé avec succès.', 'session_id': importer.import_session.id})
            else:
                return Response({'detail': 'Import terminé avec erreurs.', 'session_id': importer.import_session.id},
                                status=status.HTTP_202_ACCEPTED)

        except ValidationError as ve:
            print("ValidationError :", str(ve))
            return Response({'detail': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print("Exception complète :\n", traceback.format_exc())
            return Response({'detail': 'Une erreur est survenue : ' + str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)




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

            