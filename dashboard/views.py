from django.forms import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from users.permissions import IsSuperUser, IsGlobalAdmin, IsTerritorialAdmin, IsChefDeptTech, IsResponsableOperateur
from .services.country_statistics import CountryStatisticsService
from .services.global_statistics import GlobalStatisticsService, CountriesListStatisticsService
from .services.client_statistics import ClientStatisticsService, ClientStatisticListService, GlobalClientsListService, CountryClientStatisticsService, GlobalClientStatisticsService
from .services.policy_statistics import ClientPolicyStatisticsService, ClientPolicyListService, CountryPolicyListService, GlobalPolicyStatisticsService, CountryPolicyStatisticsService
from .services.policy_statistics import GlobalPolicyListService
from .services.partner_statistics import (GlobalPartnerStatisticsService, PartnerStatisticsService, GlobalPartnerListStatisticsService, CountryPartnerStatisticsService,
CountryPartnerListStatisticsService, ClientPartnerStatisticsService, ClientPartnerListStatisticsService, PolicyPartnerStatisticsService, PolicyPartnerListStatisticsService
)
from .services.insured_statistics import CountryInsuredStatisticsService, CountryInsuredListService
from .services.family_statistics import (
    CountryFamilyStatisticsService,
    CountryFamilyListService,
    ClientFamilyStatisticsService,
    ClientFamilyListService,
)
import traceback

import logging

logger = logging.getLogger(__name__)

class CountryStatisticsDetailView(APIView):
    """
    API endpoint to retrieve time series statistics for a specific country over a given period.
    
    This view provides comprehensive statistical data for a country including:
    - Client evolution over time
    - Premium and claim amounts
    - Insured population statistics
    - Partner consumption data
    
    Method: POST
    URL parameter: country_id (int)
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete country statistics with time series data
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def post(self, request, country_id):
        """
        Retrieve comprehensive statistics for a specific country over a given time period.
        
        This method processes date parameters, validates user permissions, and returns
        formatted statistical data including time series for various metrics.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            country_id (int): ID of the country to get statistics for
            
        Returns:
            Response: Formatted statistical data with time series for frontend consumption
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


class ClientStatisticsDetailView(APIView):
    """
    API endpoint to retrieve country-specific client statistics.
    
    This view provides statistics about clients for a specific country:
    - GET: Current totals only (minimal statistics)
    - POST: Time series statistics over a given period
    
    Method: GET/POST
    URL parameter: country_id (int)
    Permissions: Global administrators and territorial administrators
    
    Returns:
        - 200 OK: Complete country client statistics
        - 400 Bad Request: Invalid country_id or date parameters
        - 403 Forbidden: User not authorized
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def get(self, request, country_id):
        """
        Retrieve minimal country-specific client statistics with current totals only.
        
        This method returns simple statistics about clients for a specific country
        including counts, financial metrics, and calculated ratios.
        
        Args:
            request: HTTP request (no parameters required)
            country_id (int): ID of the country to get statistics for
            
        Returns:
            Response: Formatted country client statistics for dashboard cards
        """
        try:
            # Initialize the service
            statistics_service = CountryClientStatisticsService(country_id)
            
            # Get complete statistics
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in CountryClientStatisticsDetailView: {e}")
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, country_id):
        """
        Retrieve comprehensive country-specific client statistics over a given time period.
        
        This method processes date parameters and returns detailed statistical data
        for all clients in the specified country including time series.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            country_id (int): ID of the country to get statistics for
            
        Returns:
            Response: Formatted country client statistics with time series for frontend consumption
        """
        user = request.user
        date_start = request.data.get('date_start')
        date_end = request.data.get('date_end')
        
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Initialize the service with date parameters
            statistics_service = CountryStatisticsService(country_id, date_start, date_end)
            
            # Get complete country statistics
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in CountryClientStatisticsDetailView POST: {e}")
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GlobalClientStatisticsDetailView(APIView):
    """
    API endpoint to retrieve minimal global client statistics (current totals only).
    
    This view provides simple, current statistics about clients across all countries
    without time series or complex calculations. Perfect for dashboard overview cards.
    
    Method: GET
    Permissions: Global administrators and territorial administrators
    
    Returns:
        - 200 OK: Complete global client statistics with current totals
        - 403 Forbidden: User not authorized
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def get(self, request):
        """
        Retrieve minimal global client statistics with current totals only.
        
        This method returns simple statistics about clients across all countries
        including counts, financial metrics, and calculated ratios.
        
        Args:
            request: HTTP request (no parameters required)
            
        Returns:
            Response: Formatted global client statistics for dashboard cards
        """
        try:
            # Initialize the service
            statistics_service = GlobalClientStatisticsService()
            
            # Get complete statistics
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in GlobalClientStatisticsDetailView: {e}")
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GlobalStatisticsDetailView(APIView):
    """
    API endpoint to retrieve global statistics across all countries over a given period.
    
    This view provides comprehensive statistical data for all countries including:
    - Global client evolution over time
    - Total premium and claim amounts across all countries
    - Global insured population statistics
    - Cross-country partner consumption data
    - Top clients and countries consumption rankings
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete global statistics with time series data
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized (Global Admin only)
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        """
        Retrieve comprehensive global statistics across all countries over a given time period.
        
        This method processes date parameters and returns formatted statistical data
        including time series for various global metrics and cross-country comparisons.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            
        Returns:
            Response: Formatted global statistical data with time series for frontend consumption
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


class GlobalCountriesListStatisticsView(APIView):
    """
    API endpoint to retrieve statistics for the list of all countries over a given period.
    
    This view provides statistical data for all countries in a list format including:
    - Country-wise client counts
    - Country-wise premium and claim amounts
    - Country-wise insured population data
    - Country consumption rankings
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete countries list statistics
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized (Global Admin only)
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        """
        Retrieve statistics for the list of all countries over a given time period.
        
        This method processes date parameters and returns formatted statistical data
        for all countries in a list format for comparison and ranking purposes.

        Args:
            request: HTTP request containing date_start and date_end in request.data

        Returns:
            Response: Formatted countries list statistics for frontend consumption
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


class SpecificClientStatisticsDetailView(APIView):
    """
    API endpoint to retrieve comprehensive statistics for a specific client over a given period.
    
    This view provides detailed statistical data for a specific client including:
    - Client consumption patterns over time
    - Premium and claim amounts for the client
    - Insured population statistics for the client
    - Partner consumption data for the client's insured members
    
    Method: POST
    URL parameter: client_id (int)
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete client statistics with time series data
        - 400 Bad Request: Invalid date parameters or client not found
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, country_id, client_id):
        """
        Retrieve comprehensive statistics for a specific client over a given time period.
        
        This method processes date parameters, validates client existence, and returns
        formatted statistical data including time series for various client metrics.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            country_id (int): ID of the country (from URL parameter)
            client_id (int): ID of the client to get statistics for
            
        Returns:
            Response: Formatted client statistical data with time series for frontend consumption
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


class CountryClientStatisticsListView(APIView):
    """
    API endpoint to retrieve statistics list for all clients of a specific country over a given period.
    
    This view provides statistical data for all clients in a country including:
    - Client-wise consumption statistics
    - Client-wise premium and claim amounts
    - Client-wise insured population data
    - Client consumption rankings within the country
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD",
            "country_id": "int"
        }
    
    Returns:
        - 200 OK: Complete clients list statistics for the country
        - 400 Bad Request: Invalid date parameters or country not found
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def post(self, request, country_id):
        """
        Retrieve statistics list for all clients of a specific country over a given time period.
        
        This method processes date parameters and country_id, then returns formatted statistical data
        for all clients in the specified country for comparison and ranking purposes.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            country_id: Country ID passed as URL parameter
            
        Returns:
            Response: Formatted clients list statistics for the country for frontend consumption
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


class GlobalClientStatisticsListView(APIView):
    """
    API endpoint to retrieve statistics list for all clients globally over a given period.
    
    This view provides statistical data for all clients across all countries including:
    - Global client-wise consumption statistics
    - Global client-wise premium and claim amounts
    - Global client-wise insured population data
    - Global client consumption rankings across all countries
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete global clients list statistics
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]

    def post(self, request):
        """
        Retrieve statistics list for all clients globally over a given time period.
        
        This method processes date parameters and returns formatted statistical data
        for all clients across all countries for global comparison and ranking purposes.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            
        Returns:
            Response: Formatted global clients list statistics for frontend consumption
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


class GlobalPartnerStatisticsView(APIView):
    """
    API endpoint to retrieve global statistics for all partners (healthcare providers).
    
    This view provides comprehensive statistical data for all partners across all countries including:
    - Global partner consumption statistics
    - Global partner claim amounts and reimbursements
    - Global partner performance metrics
    - Cross-country partner comparisons
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
            
        Returns:
        - 200 OK: Complete global partner statistics
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized
        - 500 Internal Server Error: System error during processing
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
            service = GlobalPartnerStatisticsService(
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


class GlobalPartnerListStatisticsView(APIView):
    """
    API endpoint to retrieve a list of all partners sorted by consumption globally.
    
    This view provides a ranked list of all partners across all countries including:
    - Partner consumption rankings
    - Partner performance metrics
    - Partner claim and reimbursement data
    - Cross-country partner comparisons
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete global partners list sorted by consumption
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized
        - 500 Internal Server Error: System error during processing
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
            service = GlobalPartnerStatisticsService(
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            # Generate partners list
            partners_data = service.get_complete_statistics()
            
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
            
        Args:
            country_id (int): Country ID from URL parameter
            
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

    def post(self, request, country_id):
    
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
    
    def post(self, request, country_id):
        """
        Get list of all partners where the policy's insured members have consumed.
        
        Args:
            country_id (int): Country ID from URL parameter
            
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

    def post(self, request, country_id):
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


class CountryFamilyListView(APIView):
    """
    API endpoint to retrieve detailed list of families for a specific country over a given period.
    
    This view provides comprehensive family information including:
    - Client name and contact details
    - Policy number and creation date
    - Number of family members
    - Family consumption details for the selected period
    - Individual family member details with their consumption
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD",
            "country_id": "int"
        }
    
    Returns:
        - 200 OK: Complete families list with detailed information
        - 400 Bad Request: Invalid date parameters or country not found
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]

    def post(self, request, country_id):
        """
        Retrieve detailed list of families for a specific country over a given time period.
        
        This method processes date parameters, validates user permissions, and returns
        formatted family data including client information, policy details, and consumption
        statistics for each family member.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            country_id (int): Country ID from URL parameter
            
        Returns:
            Response: Formatted family list data with detailed information for frontend consumption
        """
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not (date_start and date_end):
                return Response(
                    {"error": "date_start et date_end sont requis."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            family_list_service = CountryFamilyListService(country_id, date_start, date_end)
            families_data = family_list_service.get_families_list()
            
            return Response(families_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in CountryFamilyListView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:      
            logger.error(f"Unexpected error in CountryFamilyListView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientFamilyStatisticsView(APIView):
    """
    API endpoint to retrieve family statistics for a specific client over a given period.
    
    This view provides comprehensive family statistical data for a specific client including:
    - Family evolution over time
    - Family consumption patterns
    - Top families consumption rankings
    - Spouse and child counts
    
    Method: POST
    URL parameter: client_id (int)
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete client family statistics with time series data
        - 400 Bad Request: Invalid date parameters or client not found
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]

    def post(self, request, client_id):
        """
        Retrieve family statistics for a specific client over a given time period.
        
        This method processes date parameters, validates user permissions, and returns
        formatted family statistical data including time series for various metrics.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            client_id (int): ID of the client to get family statistics for
            
        Returns:
            Response: Formatted family statistical data with time series for frontend consumption
        """
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not (date_start and date_end):
                return Response(
                    {"error": "date_start et date_end sont requis."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            statistics_service = ClientFamilyStatisticsService(client_id, date_start, date_end)
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in ClientFamilyStatisticsView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:      
            logger.error(f"Unexpected error in ClientFamilyStatisticsView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientFamilyListView(APIView):
    """
    API endpoint to retrieve detailed list of families for a specific client over a given period.
    
    This view provides comprehensive family information for a specific client including:
    - Family names and details
    - Policy numbers and creation dates
    - Number of family members
    - Family consumption details for the selected period
    - Individual family member details with their consumption
    
    Method: POST
    URL parameter: client_id (int)
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete families list with detailed information for the client
        - 400 Bad Request: Invalid date parameters or client not found
        - 403 Forbidden: User not authorized or account disabled
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin | IsTerritorialAdmin]

    def post(self, request, client_id):
        """
        Retrieve detailed list of families for a specific client over a given time period.
        
        This method processes date parameters, validates user permissions, and returns
        formatted family data including policy details and consumption statistics
        for each family member of the specified client.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            client_id (int): ID of the client to get family list for
            
        Returns:
            Response: Formatted family list data with detailed information for frontend consumption
        """
        if not request.user.is_active:
            return Response(
                {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération. Veuillez contacter votre administrateur hiérarchique."},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not (date_start and date_end):
                return Response(
                    {"error": "date_start et date_end sont requis."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            family_list_service = ClientFamilyListService(client_id, date_start, date_end)
            families_data = family_list_service.get_families_list()
            
            return Response(families_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in ClientFamilyListView: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:      
            logger.error(f"Unexpected error in ClientFamilyListView: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GlobalPolicyStatisticsView(APIView):
    """
    API endpoint to retrieve global policy statistics across all countries.
    
    This view provides total counts for all policies, clients, insured, and claims
    across all countries without any geographical restrictions.
    
    Method: POST
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete global policy statistics
        - 400 Bad Request: Invalid date parameters
        - 403 Forbidden: User not authorized
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]
    
    def post(self, request):
        """
        Retrieve global policy statistics across all countries.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            
        Returns:
            Response: Global policy statistics with total counts
        """
        try:
            if not request.user.is_active:
                return Response(
                    {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "Les dates de début et de fin sont requises."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            statistics_service = GlobalPolicyStatisticsService(date_start, date_end)
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in GlobalPolicyStatisticsView: {e}")
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CountryPolicyStatisticsView(APIView):
    """
    API endpoint to retrieve country-specific policy statistics.
    
    This view provides total counts for policies, clients, insured, and claims
    for a specific country with territorial access restrictions.
    
    Method: POST
    URL parameter: country_id (int)
    Request body:
        {
            "date_start": "YYYY-MM-DD",
            "date_end": "YYYY-MM-DD"
        }
    
    Returns:
        - 200 OK: Complete country policy statistics
        - 400 Bad Request: Invalid date parameters or country not found
        - 403 Forbidden: User not authorized
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]
    
    def post(self, request, country_id):
        """
        Retrieve country-specific policy statistics.
        
        Args:
            request: HTTP request containing date_start and date_end in request.data
            country_id (int): ID of the country to get statistics for
            
        Returns:
            Response: Country policy statistics with total counts
        """
        try:
            if not request.user.is_active:
                return Response(
                    {"error": "Votre compte est désactivé. Vous ne pouvez pas effectuer cette opération."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if user is territorial admin and has access to this country
            if hasattr(request.user, 'is_territorial_admin') and getattr(request.user, 'is_territorial_admin', False):
                if not hasattr(request.user, 'country') or request.user.country.id != int(country_id):
                    return Response(
                        {"error": "Vous n'avez pas accès à ce pays."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "Les dates de début et de fin sont requises."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            statistics_service = CountryPolicyStatisticsService(country_id, date_start, date_end)
            statistics_data = statistics_service.get_complete_statistics()
            
            return Response(statistics_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in CountryPolicyStatisticsView: {e}")
            traceback.print_exc()
            return Response(
                {"error": "Une erreur interne s'est produite."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class GlobalPolicyListView(APIView):
    """
    API endpoint to list policies with filtering capabilities for Global Administrators.
    
    This view provides policy listing functionality with comprehensive filtering options:
    - GET: Returns available filter options (countries, clients)
    - POST: Returns filtered policies list with statistics
    
    Supports filtering by:
    - Country selection
    - Client selection
    - Date ranges
    - Policy status
    
    Method: GET/POST
    Permissions: Global administrators only
    Access: All policies from all countries with country and client filtering
    
    Returns:
        - 200 OK: Filter options (GET) or filtered policies list (POST)
        - 400 Bad Request: Invalid filter parameters
        - 403 Forbidden: User not authorized (Global Admin only)
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def get(self, request):
        """
        Get available filter options for global administrators.
        
        Query Parameters:
            country_id (optional): Get clients for specific country
            
        Returns:
            dict: Available countries and clients for filtering
        """
        try:
            if not request.user.is_active:
                return Response(
                    {"error": "Compte utilisateur inactif."}, 
                    status=status.HTTP_403_FORBIDDEN
                )
                 
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')

            if not date_start or not date_end:
                return Response(
                    {"error": "Les dates de début et de fin sont requises."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create service instance with minimal parameters to get filter options
            service = GlobalPolicyListService(
                user=request.user,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            country_id = request.query_params.get('country_id')
            
            return Response({
                "countries": service.get_available_countries(),
                "clients": service.get_available_clients(int(country_id) if country_id else None)
            }, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in GlobalAdminPolicyListView GET: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in GlobalAdminPolicyListView GET: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request):
        """
        Get filtered policies list with statistics for global administrators.
        
        Request Body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            country_id (int, optional): Filter by country
            client_id (int, optional): Filter by client
            
        Returns:
            dict: Complete policies data with statistics and filter options
        """
        try:
            if not request.user.is_active:
                return Response(
                    {"error": "Compte utilisateur inactif."}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            

            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            country_id = request.data.get('country_id')
            client_id = request.data.get('client_id')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "Les dates de début et de fin sont requises."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create service and get complete data
            service = GlobalPolicyListService(
                user=request.user,
                date_start_str=date_start,
                date_end_str=date_end,
                country_id=int(country_id) if country_id else None,
                client_id=int(client_id) if client_id else None
            )
            
            complete_data = service.get_complete_data()
            return Response(complete_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in GlobalAdminPolicyListView POST: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in GlobalAdminPolicyListView POST: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CountryPolicyListView(APIView):
    """
    API endpoint to list policies with filtering capabilities for Territorial Administrators.
    
    This view provides policy listing functionality with country-restricted filtering options:
    - GET: Returns available filter options (clients from their assigned country)
    - POST: Returns filtered policies list with statistics from their assigned country
    
    Supports filtering by:
    - Client selection (from assigned country only)
    - Date ranges
    - Policy status
    
    Method: GET/POST
    Permissions: Territorial administrators only
    Access: Only policies from the admin's assigned country with client filtering
    
    Returns:
        - 200 OK: Filter options (GET) or filtered policies list (POST)
        - 400 Bad Request: Invalid filter parameters
        - 403 Forbidden: User not authorized (Territorial Admin only)
        - 500 Internal Server Error: System error during processing
    """
    permission_classes = [IsAuthenticated, IsTerritorialAdmin]
    
    def get(self, request):
        """
        Get available filter options for territorial administrators.
        
        Returns:
            dict: Available clients for filtering (from admin's country)
        """
        try:
            if not request.user.is_active:
                return Response(
                    {"error": "Compte utilisateur inactif."}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')

            if not date_start or not date_end:
                return Response(
                    {"error": "Les dates de début et de fin sont requises."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Create service instance with minimal parameters to get filter options
            service = CountryPolicyListService(
                user=request.user,
                date_start_str=date_start,
                date_end_str=date_end
            )
            
            return Response({
                "clients": service.get_available_clients(),
                "country_context": {
                    "id": service.assigned_country.id,
                    "name": service.assigned_country.name,
                    "code": getattr(service.assigned_country, 'code', '')
                }
            }, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in CountryPolicyListView GET: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in CountryPolicyListView GET: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, country_id):
        """
        Get filtered policies list with statistics for territorial administrators.
        
        Args:
            country_id (int): Country ID from URL parameter
            
        Request Body:
            date_start (str): Start date in YYYY-MM-DD format
            date_end (str): End date in YYYY-MM-DD format
            client_id (int, optional): Filter by client
            
        Returns:
            dict: Complete policies data with statistics and filter options
        """
        try:
            if not request.user.is_active:
                return Response(
                    {"error": "Compte utilisateur inactif."}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Extract and validate request data
            date_start = request.data.get('date_start')
            date_end = request.data.get('date_end')
            client_id = request.data.get('client_id')
            
            if not date_start or not date_end:
                return Response(
                    {"error": "Les dates de début et de fin sont requises."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create service and get complete data
            service = CountryPolicyListService(
                user=request.user,
                date_start_str=date_start,
                date_end_str=date_end,
                client_id=int(client_id) if client_id else None
            )
            
            complete_data = service.get_complete_data()
            return Response(complete_data, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            logger.error(f"Validation error in CountryPolicyListView POST: {e}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in CountryPolicyListView POST: {e}")
            return Response(
                {"error": "Une erreur inattendue s'est produite."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

