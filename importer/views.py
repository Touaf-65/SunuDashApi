from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from users.permissions import IsTerritorialAdmin,IsTerritorialAdminAndAssignedCountry, IsChefDeptTech
from .services.importer_service import ImporterService
from .utils.functions import open_excel_csv

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
            success = importer.run()
            if success:
                return Response({'detail': 'Import lancé avec succès.', 'session_id': importer.import_session.id})
            else:
                return Response({'detail': 'Import terminé avec erreurs.', 'session_id': importer.import_session.id},
                                status=status.HTTP_202_ACCEPTED)
        except ValidationError as ve:
            return Response({'detail': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'detail': 'Une erreur est survenue : ' + str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
