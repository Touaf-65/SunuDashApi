from django.db.models import Sum, Count, Q
from core.models import Client, Claim, Invoice, InsuredEmployer, Policy
from users.models import CustomUser
from .base import parse_date_range

class ClientStatisticsService:
    """
    Service to generate statistics for clients of a country over a given period.
    """
    
    def __init__(self, country_id, date_start_str, date_end_str):
        """
        Initializes the service with the basic parameters.
        
        Args:
            country_id (int): Country ID
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.country_id = country_id
        self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
        
        # Preparation of base data
        self.clients = Client.objects.filter(country_id=country_id)
    
    def get_client_statistics_list(self):
        """
        Generates the list of statistics for all clients in the country.
        
        Returns:
            list: List of statistics by client
        """
        results = []
        
        for client in self.clients:
            client_stats = self._calculate_client_stats(client)
            results.append(client_stats)
        
        return results
    
    def get_client_statistics_optimized(self):
        """
        Optimized version with fewer SQL queries.
        
        Returns:
            list: List of statistics by client (optimized)
        """
        # Preloading data to avoid N+1 queries
        clients_data = self._prefetch_clients_data()
        policies_data = self._prefetch_policies_data()
        insured_data = self._prefetch_insured_data()
        claims_data = self._prefetch_claims_data()
        invoices_data = self._prefetch_invoices_data()
        
        results = []
        
        for client in self.clients:
            client_stats = self._calculate_optimized_client_stats(
                client, policies_data, insured_data, claims_data, invoices_data
            )
            results.append(client_stats)
        
        return results
    
    def get_filtered_client_statistics(self, filters=None):
        """
        Generates client statistics with custom filters.
        
        Args:
            filters (dict): Dictionary of optional filters
                - min_consumption: Minimum consumption
                - min_insured: Minimum number of insured
                - has_claims: True for clients with claims only
                
        Returns:
            list: Filtered list of statistics by client
        """
        if filters is None:
            filters = {}
        
        results = self.get_client_statistics_optimized()
        
        # Applying filters
        if filters.get('min_consumption'):
            results = [r for r in results if r['total_consumption'] >= filters['min_consumption']]
        
        if filters.get('min_insured'):
            results = [r for r in results if r['nb_total_insured'] >= filters['min_insured']]
        
        if filters.get('has_claims'):
            results = [r for r in results if r['total_consumption'] > 0]
        
        return results
    
    def get_client_summary_statistics(self):
        """
        Generates summary statistics for all clients.
        
        Returns:
            dict: Aggregated statistics
        """
        client_stats = self.get_client_statistics_optimized()
        
        if not client_stats:
            return {
                "total_clients": 0,
                "total_policies": 0,
                "total_insured": 0,
                "total_primary_insured": 0,
                "total_consumption": 0,
                "total_reimbursement": 0,
                "avg_consumption_per_client": 0,
                "clients_with_claims": 0
            }
        
        total_consumption = sum(c['total_consumption'] for c in client_stats)
        total_reimbursement = sum(c['total_reimbursement'] for c in client_stats)
        clients_with_claims = len([c for c in client_stats if c['total_consumption'] > 0])
        
        return {
            "total_clients": len(client_stats),
            "total_policies": sum(c['nb_policies'] for c in client_stats),
            "total_insured": sum(c['nb_total_insured'] for c in client_stats),
            "total_primary_insured": sum(c['nb_primary_insured'] for c in client_stats),
            "total_consumption": float(total_consumption),
            "total_reimbursement": float(total_reimbursement),
            "avg_consumption_per_client": float(total_consumption / len(client_stats)),
            "clients_with_claims": clients_with_claims,
            "claims_ratio": round(clients_with_claims / len(client_stats) * 100, 2)
        }
    
    def _calculate_client_stats(self, client):
        """
        Calculates statistics for a given client (original version).
        
        Args:
            client: Instance of the Client model
            
        Returns:
            dict: Client statistics
        """
        # Number of policies
        nb_policies = Policy.objects.filter(client=client).count()
        
        # Insured data
        insured_links = InsuredEmployer.objects.filter(employer=client)
        nb_primary = insured_links.filter(role='primary').count()
        nb_total = insured_links.count()
        
        # Claims and consumption
        insured_ids = list(insured_links.values_list('insured_id', flat=True))
        claims = Claim.objects.filter(
            insured_id__in=insured_ids,
            claim_date__range=(self.date_start, self.date_end)
        )
        
        invoice_ids = list(claims.values_list('invoice_id', flat=True))
        total_consumption = Invoice.objects.filter(
            id__in=invoice_ids
        ).aggregate(total=Sum('claimed_amount'))['total'] or 0
        
        total_reimbursement = Invoice.objects.filter(
            id__in=invoice_ids
        ).aggregate(total=Sum('reimbursed_amount'))['total'] or 0
        
        return {
            "client_id": client.id,
            "client_name": client.name,
            "contact": client.contact,
            "nb_policies": nb_policies,
            "nb_primary_insured": nb_primary,
            "nb_total_insured": nb_total,
            "total_consumption": float(total_consumption),
            "total_reimbursement": float(total_reimbursement)
        }
    
    def _prefetch_clients_data(self):
        """Preloads client data."""
        return self.clients.select_related().values(
            'id', 'name', 'contact'
        )
    
    def _prefetch_policies_data(self):
        """Preloads the number of policies per client."""
        return dict(
            Policy.objects.filter(client_id__in=self.clients.values_list('id', flat=True))
            .values('client_id')
            .annotate(count=Count('id'))
            .values_list('client_id', 'count')
        )
    
    def _prefetch_insured_data(self):
        """Preloads insured data per client."""
        insured_data = {}
        
        # Count all insured per client
        total_insured = dict(
            InsuredEmployer.objects.filter(employer_id__in=self.clients.values_list('id', flat=True))
            .values('employer_id')
            .annotate(count=Count('insured_id', distinct=True))
            .values_list('employer_id', 'count')
        )
        
        # Count primary insured per client
        primary_insured = dict(
            InsuredEmployer.objects.filter(
                employer_id__in=self.clients.values_list('id', flat=True),
                role='primary'
            )
            .values('employer_id')
            .annotate(count=Count('insured_id', distinct=True))
            .values_list('employer_id', 'count')
        )
        
        # List insured IDs by client
        insured_ids_by_client = {}
        for link in InsuredEmployer.objects.filter(employer_id__in=self.clients.values_list('id', flat=True)):
            if link.employer_id not in insured_ids_by_client:
                insured_ids_by_client[link.employer_id] = []
            insured_ids_by_client[link.employer_id].append(link.insured_id)
        
        return {
            'total': total_insured,
            'primary': primary_insured,
            'ids': insured_ids_by_client
        }
    
    def _prefetch_claims_data(self):
        """Preloads claims data."""
        return Claim.objects.filter(
            claim_date__range=(self.date_start, self.date_end)
        ).select_related('invoice')
    
    def _prefetch_invoices_data(self):
        """Preloads invoice data with aggregation."""
        # Retrieve claims in the period
        claims_in_period = Claim.objects.filter(
            claim_date__range=(self.date_start, self.date_end)
        ).values_list('invoice_id', 'insured_id').distinct()
        
        # Create a mapping invoice_id -> insured_id
        invoice_to_insured = {claim[0]: claim[1] for claim in claims_in_period}
        
        # Retrieve invoice data
        invoices = Invoice.objects.filter(
            id__in=invoice_to_insured.keys()
        ).values('id', 'claimed_amount', 'reimbursed_amount')
        
        return {
            'invoice_to_insured': invoice_to_insured,
            'invoices': {inv['id']: inv for inv in invoices}
        }
    
    def _calculate_optimized_client_stats(self, client, policies_data, insured_data, claims_data, invoices_data):
        """
        Optimized version of client statistics calculation.
        
        Args:
            client: Instance of the client
            policies_data: Preloaded policy data
            insured_data: Preloaded insured data
            claims_data: Preloaded claims data
            invoices_data: Preloaded invoice data
            
        Returns:
            dict: Client statistics
        """
        client_id = client.id
        
        # Number of policies
        nb_policies = policies_data.get(client_id, 0)
        
        # Number of insured
        nb_total = insured_data['total'].get(client_id, 0)
        nb_primary = insured_data['primary'].get(client_id, 0)
        
        # Calculate consumption
        client_insured_ids = insured_data['ids'].get(client_id, [])
        total_consumption = 0
        total_reimbursement = 0
        
        for invoice_id, insured_id in invoices_data['invoice_to_insured'].items():
            if insured_id in client_insured_ids:
                invoice_data = invoices_data['invoices'].get(invoice_id, {})
                total_consumption += float(invoice_data.get('claimed_amount', 0))
                total_reimbursement += float(invoice_data.get('reimbursed_amount', 0))
        
        return {
            "client_id": client_id,
            "client_name": client.name,
            "contact": client.contact,
            "nb_policies": nb_policies,
            "nb_primary_insured": nb_primary,
            "nb_total_insured": nb_total,
            "total_consumption": total_consumption,
            "total_reimbursement": total_reimbursement
        }


class ClientPermissionService:
    """
    Service to manage access permissions for client statistics.
    """
    
    @staticmethod
    def get_allowed_country_id(user, requested_country_id=None):
        """
        Determines the ID of the country that the user has access to.
        
        Args:
            user: Instance of the user
            requested_country_id: ID of the requested country (optional)
            
        Returns:
            int: Allowed country ID
            
        Raises:
            PermissionError: If the user does not have permissions
            ValueError: If the parameters are invalid
        """
        if user.role in [CustomUser.Roles.ADMIN_GLOBAL, CustomUser.Roles.SUPERUSER]:
            if not requested_country_id:
                raise ValueError("country_id is required for superusers and global admins.")
            return requested_country_id
        else:
            if not hasattr(user, 'country') or not user.country:
                raise ValueError("No country associated with this user.")
            
            user_country_id = user.country.id
            
            if requested_country_id and int(requested_country_id) != user_country_id:
                raise PermissionError("You can only access your own country.")
            
            return user_country_id
    
    @staticmethod
    def validate_user_access(user, country_id):
        """
        Validates that the user has access to the specified country.
        
        Args:
            user: Instance of the user
            country_id: ID of the country
            
        Returns:
            bool: True if access is allowed
            
        Raises:
            PermissionError: If access is not allowed
        """
        try:
            allowed_country_id = ClientPermissionService.get_allowed_country_id(user, country_id)
            return allowed_country_id == country_id
        except (PermissionError, ValueError):
            raise PermissionError("Unauthorized access to this country.")
