from django.forms import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from users.permissions import IsSuperUser, IsGlobalAdmin, IsTerritorialAdmin, IsChefDeptTech, IsResponsableOperateur
from .services.country_statistics import CountryStatisticsService
from .services.global_statistics import GlobalStatisticsService, CountriesListStatisticsService
from .services.client_statistics import ClientStatisticsService, ClientStatisticListService, GlobalClientsListService
from .services.policy_statistics import ClientPolicyStatisticsService, ClientPolicyListStatisticsService
from .services.partner_statistics import (PartnerStatisticsService, PartnerListStatisticsService, CountryPartnerStatisticsService,
CountryPartnerListStatisticsService, ClientPartnerStatisticsService, ClientPartnerListStatisticsService, PolicyPartnerStatisticsService,
)
from .services.insured_statistics import CountryInsuredStatisticsService, CountryInsuredListService, CountryFamilyStatisticsService 
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
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

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
                {"error": "Erreur interne du serveur."},
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


class GlobalClientStatisticListView(APIView):
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def post(self, request):
        
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
            service = GlobalClientsListService(date_start, date_end)
            
            statistics = service.get_all_clients_statistics_list()
            
            return Response(statistics, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in GlobalClientStatisticListView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in GlobalClientStatisticListView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientPolicyStatisticsView(APIView):
    """
    API View for policy statistics using ClientPolicyStatisticsService.
    Generates comprehensive statistics for a specific policy within a date range.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]

    def post(self, request, policy_id):
        """
        Generate comprehensive statistics for a specific policy.
        
        Args:
            request: HTTP request with date_start and date_end
            policy_id: ID of the policy to analyze
            
        Returns:
            Response: JSON response with all policy statistics
        """
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Extract and validate input parameters
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not (date_start and date_end):
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize the service
            logger.info(f"Generating policy statistics for policy {policy_id} from {date_start} to {date_end}")
            policy_service = ClientPolicyStatisticsService(policy_id, date_start, date_end)
            
            # Check if policy exists
            if not policy_service.policy:
                return Response(
                    {"error": f"Police {policy_id} non trouvée."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Generate statistics
            statistics_data = policy_service.generate_statistics()
            
            if not statistics_data:
                return Response(
                    {"error": "Erreur lors de la génération des statistiques de la police."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            logger.info(f"Successfully generated policy statistics for policy {policy_id}")
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValueError as e:
            logger.error(f"Validation error in policy statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in policy statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientPolicyListStatisticsView(APIView):
    """
    API view to get statistics for all policies of a specific client.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request):
        """
        Generate statistics for all policies of a client.
        
        Args:
            client_id (int): ID of the client
            
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with policies statistics
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            client_id = request.data.get('client_id')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = ClientPolicyListStatisticsService(
                client_id=client_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate statistics
            statistics = service.get_policies_statistics()
            
            return Response(statistics, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in client policy list statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in client policy list statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in client policy list statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PartnerStatisticsView(APIView):
    """
    API view to get global statistics for all partners (prestataires).
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request):
        """
        Generate global statistics for all partners.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partners statistics
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = PartnerStatisticsService(
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate statistics
            statistics = service.get_complete_statistics()
            
            return Response(statistics, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in partner statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PartnerListStatisticsView(APIView):
    """
    API view to get a list of all partners sorted by consumption.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request):
        """
        Generate list of all partners sorted by consumption.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partners list and summary
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = PartnerListStatisticsService(
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate partners list
            partners_data = service.get_complete_partners_list()
            
            return Response(partners_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in partner list statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in partner list statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in partner list statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CountryPartnerStatisticsView(APIView):
    """
    API view to get partner statistics for a specific country.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request, country_id):
        """
        Generate partner statistics for a specific country.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partner statistics for the country
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = CountryPartnerStatisticsService(
                country_id=country_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate statistics
            stats = service.get_complete_statistics()
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in country partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in country partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in country partner statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CountryPartnerListStatisticsView(APIView):
    """
    API view to get a list of all partners for a specific country, sorted by consumption.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request, country_id):
        """
        Get list of all partners for a specific country, sorted by consumption.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partners list and summary
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = CountryPartnerListStatisticsService(
                country_id=country_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate partners list
            partners_data = service.get_complete_partners_list()
            
            return Response(partners_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in country partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in country partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in country partner list: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientPartnerStatisticsView(APIView):
    """
    API view to get partner statistics for a specific client.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request, client_id):
        """
        Generate partner statistics for a specific client.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partner statistics for the client
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = ClientPartnerStatisticsService(
                client_id=client_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate statistics
            stats = service.get_complete_statistics()
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in client partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in client partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in client partner statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientPartnerListStatisticsView(APIView):
    """
    API view to get a list of all partners where a client's insured members have consumed,
    sorted by consumption.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request, client_id):
        """
        Get list of all partners where the client's insured members have consumed.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partners list and summary
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = ClientPartnerListStatisticsService(
                client_id=client_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate partners list
            partners_data = service.get_complete_partners_list()
            
            return Response(partners_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in client partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in client partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in client partner list: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PolicyPartnerStatisticsView(APIView):
    """
    API view to get partner statistics for a specific policy.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request, policy_id):
        """
        Generate partner statistics for a specific policy.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partner statistics for the policy
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = PolicyPartnerStatisticsService(
                policy_id=policy_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate statistics
            stats = service.get_complete_statistics()
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in policy partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in policy partner statistics: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in policy partner statistics: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PolicyPartnerListStatisticsView(APIView):
    """
    API view to get a list of all partners where a policy's insured members have consumed,
    sorted by consumption.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request, policy_id):
        """
        Get list of all partners where the policy's insured members have consumed.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partners list and summary
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = PolicyPartnerListStatisticsService(
                policy_id=policy_id,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate partners list
            partners_data = service.get_complete_partners_list()
            
            return Response(partners_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in policy partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in policy partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in policy partner list: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




class PartnerStatisticsView(APIView):
    """
    API View for client statistics using ClientStatisticsService.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, partner_id):
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
            service = PartnerStatisticsService(partner_id, date_start, date_end)
            
            statistics = service.get_complete_statistics()
            
            return Response(statistics, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in PartnerStatisticsView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in PartnerStatisticsView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




class CountryInsuredStatisticsView(APIView):
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
            service = CountryInsuredStatisticsService(country_id, date_start, date_end)
            
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



class CountryInsuredListStatisticsView(APIView):
    """
    API view to get a list of all partners where a policy's insured members have consumed,
    sorted by consumption.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]
    
    def post(self, request):
        """
        Get list of all partners where the policy's insured members have consumed.
        
        Request body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            
        Returns:
            Response: JSON response with partners list and summary
        """
        try:
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            country_id = request.data.get('country_id')

            if not date_start or not date_end:
                return Response(
                    {"error": "date_start et date_end sont requis."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize and use the service
            service = CountryInsuredListService(
                country_id=country_id
            )
            
            # Generate partners list
            insureds_data = service.get_complete_insureds_list()
            
            return Response(insureds_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in policy partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.error(f"Value error in policy partner list: {e}")
            return Response(
                {"error": f"Erreur de validation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in policy partner list: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": "Erreur interne du serveur."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CountryFamilyStatisticsView(APIView):
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]

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
            service = CountryFamilyStatisticsService(country_id, date_start, date_end)
            statistics = service.get_complete_statistics()
            return Response(statistics, status=status.HTTP_200_OK)
        except ValidationError as e:
            logger.error(f"Validation error in CountryFamilyStatisticsView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:      
            logger.error(f"Unexpected error in CountryFamilyStatisticsView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
