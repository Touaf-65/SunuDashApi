from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from users.permissions import IsSuperUser, IsGlobalAdmin, IsTerritorialAdmin
from .services.country_statistics import CountryStatisticsService
import traceback


class CountryStatisticsDetailView(APIView):
    """
    Vue pour récupérer les séries temporelles statistiques d'un pays donné sur une période.
    Utilise le service CountryStatisticsService pour la logique métier.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]

    def post(self, request, country_id):
        """
        Récupère les statistiques d'un pays sur une période donnée.
        
        Args:
            request: Requête HTTP contenant date_start et date_end
            country_id (int): ID du pays
            
        Returns:
            Response: Données statistiques formatées pour le frontend
        """
        try:
            # Extraction des paramètres
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            # Initialisation du service
            statistics_service = CountryStatisticsService(country_id, date_start, date_end)
            
            # Génération des statistiques complètes
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValueError as e:
            # Erreurs de validation des paramètres
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            # Erreurs système
            print("ERREUR API CountryStatisticsDetailView:", str(e))
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

