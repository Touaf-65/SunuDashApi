from django.forms import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from users.permissions import IsSuperUser, IsGlobalAdmin, IsTerritorialAdmin, IsChefDeptTech, IsResponsableOperateur
from .services.country_statistics import CountryStatisticsService
from .services.global_statistics import GlobalStatisticsService, CountriesListStatisticsService
from .services.client_statistics import ClientStatisticsService, ClientStatisticListService
import traceback

import logging

logger = logging.getLogger(__name__)

class CountryStatisticsDetailView(APIView):
    """
    Vue pour récupérer les séries temporelles statistiques d'un pays donné sur une période.
    Utilise le service CountryStatisticsService pour la logique métier.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin, IsTerritorialAdmin, IsChefDeptTech]

    def post(self, request, country_id):
        """
        Récupère les statistiques d'un pays sur une période donnée.
        
        Args:
            request: Requête HTTP contenant date_start et date_end
            country_id (int): ID du pays
            
        Returns:
            Response: Données statistiques formatées pour le frontend
        """
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            statistics_service = CountryStatisticsService(country_id, date_start, date_end)
            
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValueError as e:
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


class GlobalStatisticsDetailView(APIView):
    """
    Vue pour récupérer les séries temporelles statistiques d'un pays donné sur une période.
    Utilise le service CountryStatisticsService pour la logique métier.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin, IsTerritorialAdmin, IsChefDeptTech]

    def post(self, request):
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
            global_statistics_service = GlobalStatisticsService(date_start, date_end)
            
            # Génération des statistiques complètes
            global_statistics_data = global_statistics_service.get_complete_statistics()
            
            return Response(global_statistics_data, status=status.HTTP_200_OK)
            
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


class CountriesListStatisticsView(APIView):
    """
    Vue pour récupérer les statistiques globales de la liste des pays sur une période donnée.
    Utilise le service CountriesListStatisticsService pour la logique métier.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        """
        Récupère les statistiques globales pour la liste des pays sur une période donnée.

        Args:
            request: Requête HTTP contenant date_start et date_end

        Returns:
            Response: Données statistiques formatées pour le frontend
        """
        try:
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')

            countries_list_statistics_service = CountriesListStatisticsService(date_start, date_end)
            countries_list_statistics_data = countries_list_statistics_service.get_countries_statistics()

            return Response(countries_list_statistics_data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            print("ERREUR API CountriesListStatisticsView:", str(e))
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientStatisticView(APIView):
    """
    API View for client statistics using ClientStatisticsService.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, client_id):
        """
        Generate comprehensive statistics for a specific client.
        
        Args:
            request: HTTP request with date_start and date_end
            client_id: ID of the client
            
        Returns:
            Response: JSON response with all client statistics
        """
        user = request.user
        date_start = request.data.get('date_start')
        date_end = request.data.get('date_end')
        
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not (date_start and date_end):
            return Response(
                {"error": "date_start et date_end sont requis."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = ClientStatisticsService(client_id, date_start, date_end)
            
            statistics = service.get_complete_statistics()
            
            return Response(statistics, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in ClientStatisticView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in ClientStatisticView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientStatisticListView(APIView):
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def post(self, request):
    
        user = request.user
        date_start = request.data.get('date_start')
        date_end = request.data.get('date_end')
        country_id = request.data.get('country_id')
        
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not (date_start and date_end):
            return Response(
                {"error": "date_start et date_end sont requis."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = ClientStatisticListService(country_id, date_start, date_end)
            
            statistics = service.get_clients_statistics_list()
            
            return Response(statistics, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in ClientStatisticView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in ClientStatisticView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

