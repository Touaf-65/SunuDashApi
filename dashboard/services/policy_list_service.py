from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError
from core.models import Policy, Client, Claim, Invoice, InsuredEmployer
from countries.models import Country
from users.models import CustomUser
from .base import parse_date_range, sanitize_float
import logging

logger = logging.getLogger(__name__)


class GlobalAdminPolicyListService:
    """
    Service to retrieve and filter policies for Global Administrators only.
    
    Features:
    - Access to all policies from all countries
    - Filter by country (select dropdown)
    - Filter by client (searchfield that updates based on selected country)
    - Dynamic filtering with country and client selection
    - Complete statistics for each policy
    """
    
    def __init__(self, user, date_start_str, date_end_str, country_id=None, client_id=None):
        """
        Initialize the service with user context and filters.
        
        Args:
            user: Current user (CustomUser instance) - must be global admin
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
            country_id (int, optional): Filter by country ID
            client_id (int, optional): Filter by client ID
        """
        try:
            self.user = user
            self.country_id = int(country_id) if country_id else None
            self.client_id = int(client_id) if client_id else None
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_user_permissions()
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PolicyListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_user_permissions(self):
        """
        Setup user permissions - validates that user is global admin.
        """
        try:
            self.is_global_admin = (
                self.user.is_superuser or 
                getattr(self.user, 'is_global_admin', False)
            )
            
            if not self.is_global_admin:
                raise ValidationError("Ce service est réservé aux administrateurs globaux uniquement.")
            
            # Global admin can access all countries
            self.accessible_countries = Country.objects.filter(is_active=True)
            self.accessible_country_ids = list(self.accessible_countries.values_list('id', flat=True))
            
            logger.info(f"Global admin {self.user.email} - Access to all {len(self.accessible_country_ids)} countries")
            
        except Exception as e:
            logger.error(f"Error setting up user permissions: {e}")
            raise ValidationError(f"Error setting up permissions: {e}")
    
    def _setup_base_filters(self):
        """
        Set up base querysets for policies - global admin has access to all policies.
        """
        try:
            # Start with base policies query - global admin sees all policies
            policies_query = Policy.objects.select_related('client', 'client__country')
            
            # Apply country filter if specified
            if self.country_id:
                policies_query = policies_query.filter(client__country_id=self.country_id)
            
            # Apply client filter if specified
            if self.client_id:
                policies_query = policies_query.filter(client_id=self.client_id)
            
            self.policies = policies_query
            
            logger.info(f"Global admin {self.user.email}: {self.policies.count()} policies found with current filters")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_available_countries(self):
        """
        Get list of countries available for filtering based on user permissions.
        
        Returns:
            list: List of country dictionaries
        """
        try:
            countries = []
            for country in self.accessible_countries:
                # Count policies in this country
                policy_count = Policy.objects.filter(
                    client__country_id=country.id
                ).count()
                
                countries.append({
                    "id": country.id,
                    "name": country.name,
                    "code": country.code,
                    "policy_count": policy_count
                })
            
            return countries
            
        except Exception as e:
            logger.error(f"Error getting available countries: {e}")
            return []
    
    def get_available_clients(self, country_id=None):
        """
        Get list of clients available for filtering.
        
        Args:
            country_id (int, optional): Filter clients by country
            
        Returns:
            list: List of client dictionaries
        """
        try:
            clients_query = Client.objects.select_related('country')
            
            # Global admin can access all clients
            
            # Apply country filter if specified
            if country_id:
                clients_query = clients_query.filter(country_id=country_id)
            
            clients = []
            for client in clients_query:
                # Count policies for this client
                policy_count = Policy.objects.filter(client_id=client.id).count()
                
                clients.append({
                    "id": client.id,
                    "name": client.name,
                    "contact": client.contact or "",
                    "country_id": client.country.id if client.country else None,
                    "country_name": client.country.name if client.country else None,
                    "policy_count": policy_count
                })
            
            return clients
            
        except Exception as e:
            logger.error(f"Error getting available clients: {e}")
            return []
    
    def get_policies_list(self):
        """
        Get list of policies with detailed statistics.
        
        Returns:
            list: List of policy dictionaries with statistics
        """
        try:
            results = []
            
            for policy in self.policies:
                policy_stats = self._get_policy_statistics(policy)
                results.append(policy_stats)
            
            # Sort by total claimed amount descending
            results.sort(key=lambda x: x['total_claimed_amount'], reverse=True)
            
            return sanitize_float(results)
            
        except Exception as e:
            logger.error(f"Error generating policies list: {e}")
            return []
    
    def _get_policy_statistics(self, policy):
        """
        Get statistics for a single policy.
        
        Args:
            policy: Policy object
            
        Returns:
            dict: Policy statistics
        """
        try:
            # Get insured employees for this policy's client
            insured_links = InsuredEmployer.objects.select_related('insured').filter(
                employer=policy.client
            )
            nb_insured = insured_links.count()
            nb_primary_insured = insured_links.filter(role='primary').count()
            
            # Get insured IDs for claims filtering
            insured_ids = list(insured_links.values_list('insured_id', flat=True))
            
            # Get claims for this policy in the date range
            claims = Claim.objects.select_related('invoice').filter(
                Q(insured_id__in=insured_ids) | Q(policy_id=policy.id),
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Calculate amounts and statistics
            amounts_data = claims.aggregate(
                total_claimed=Sum('invoice__claimed_amount'),
                total_reimbursed=Sum('invoice__reimbursed_amount')
            )
            
            total_claimed_amount = float(amounts_data['total_claimed'] or 0)
            total_reimbursed_amount = float(amounts_data['total_reimbursed'] or 0)
            
            return {
                "policy_id": policy.id,
                "policy_number": getattr(policy, 'policy_number', f"POL-{policy.id}"),
                "client": {
                    "id": policy.client.id,
                    "name": policy.client.name,
                    "contact": policy.client.contact or "",
                    "country": {
                        "id": policy.client.country.id if policy.client.country else None,
                        "name": policy.client.country.name if policy.client.country else None
                    }
                },
                "insured_statistics": {
                    "total_insured": nb_insured,
                    "primary_insured": nb_primary_insured,
                    "dependents": nb_insured - nb_primary_insured
                },
                "financial_statistics": {
                    "total_claimed_amount": total_claimed_amount,
                    "total_reimbursed_amount": total_reimbursed_amount,
                    "reimbursement_rate": (total_reimbursed_amount / total_claimed_amount * 100) if total_claimed_amount > 0 else 0.0
                },
                "claims_count": claims.count(),
                "policy_dates": {
                    "start_date": policy.start_date.isoformat() if hasattr(policy, 'start_date') and policy.start_date else None,
                    "end_date": policy.end_date.isoformat() if hasattr(policy, 'end_date') and policy.end_date else None
                },
                "is_active": getattr(policy, 'is_active', True)
            }
            
        except Exception as e:
            logger.error(f"Error calculating statistics for policy {policy.id}: {e}")
            return {
                "policy_id": policy.id,
                "policy_number": getattr(policy, 'policy_number', f"POL-{policy.id}"),
                "client": {
                    "id": policy.client.id,
                    "name": policy.client.name,
                    "contact": policy.client.contact or "",
                    "country": {
                        "id": policy.client.country.id if policy.client.country else None,
                        "name": policy.client.country.name if policy.client.country else None
                    }
                },
                "insured_statistics": {
                    "total_insured": 0,
                    "primary_insured": 0,
                    "dependents": 0
                },
                "financial_statistics": {
                    "total_claimed_amount": 0.0,
                    "total_reimbursed_amount": 0.0,
                    "reimbursement_rate": 0.0
                },
                "claims_count": 0,
                "policy_dates": {
                    "start_date": None,
                    "end_date": None
                },
                "is_active": getattr(policy, 'is_active', True)
            }
    
    def get_summary_statistics(self):
        """
        Get summary statistics for the filtered policies.
        
        Returns:
            dict: Summary statistics
        """
        try:
            policies_list = self.get_policies_list()
            
            if not policies_list:
                return {
                    "total_policies": 0,
                    "total_clients": 0,
                    "total_countries": 0,
                    "total_insured": 0,
                    "total_claimed_amount": 0.0,
                    "total_reimbursed_amount": 0.0,
                    "total_claims": 0,
                    "average_claimed_per_policy": 0.0,
                    "average_reimbursed_per_policy": 0.0,
                    "overall_reimbursement_rate": 0.0
                }
            
            total_policies = len(policies_list)
            unique_clients = len(set(policy['client']['id'] for policy in policies_list))
            unique_countries = len(set(
                policy['client']['country']['id'] 
                for policy in policies_list 
                if policy['client']['country']['id'] is not None
            ))
            total_insured = sum(policy['insured_statistics']['total_insured'] for policy in policies_list)
            total_claimed = sum(policy['financial_statistics']['total_claimed_amount'] for policy in policies_list)
            total_reimbursed = sum(policy['financial_statistics']['total_reimbursed_amount'] for policy in policies_list)
            total_claims = sum(policy['claims_count'] for policy in policies_list)
            
            return sanitize_float({
                "total_policies": total_policies,
                "total_clients": unique_clients,
                "total_countries": unique_countries,
                "total_insured": total_insured,
                "total_claimed_amount": total_claimed,
                "total_reimbursed_amount": total_reimbursed,
                "total_claims": total_claims,
                "average_claimed_per_policy": total_claimed / total_policies if total_policies > 0 else 0.0,
                "average_reimbursed_per_policy": total_reimbursed / total_policies if total_policies > 0 else 0.0,
                "overall_reimbursement_rate": (total_reimbursed / total_claimed * 100) if total_claimed > 0 else 0.0
            })
            
        except Exception as e:
            logger.error(f"Error generating summary statistics: {e}")
            return {
                "total_policies": 0,
                "total_clients": 0,
                "total_countries": 0,
                "total_insured": 0,
                "total_claimed_amount": 0.0,
                "total_reimbursed_amount": 0.0,
                "total_claims": 0,
                "average_claimed_per_policy": 0.0,
                "average_reimbursed_per_policy": 0.0,
                "overall_reimbursement_rate": 0.0
            }
    
    def get_complete_data(self):
        """
        Get complete data including policies, filters options, and summary.
        
        Returns:
            dict: Complete data structure for frontend
        """
        try:
            return {
                "policies": self.get_policies_list(),
                "summary": self.get_summary_statistics(),
                "filter_options": {
                    "countries": self.get_available_countries(),
                    "clients": self.get_available_clients(self.country_id)
                },
                "applied_filters": {
                    "country_id": self.country_id,
                    "client_id": self.client_id,
                    "date_start": self.date_start.isoformat(),
                    "date_end": self.date_end.isoformat()
                },
                "user_context": {
                    "is_global_admin": self.is_global_admin,
                    "accessible_countries_count": len(self.accessible_country_ids)
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating complete data: {e}")
            return {
                "policies": [],
                "summary": self.get_summary_statistics(),
                "filter_options": {
                    "countries": [],
                    "clients": []
                },
                "applied_filters": {
                    "country_id": self.country_id,
                    "client_id": self.client_id,
                    "date_start": self.date_start.isoformat(),
                    "date_end": self.date_end.isoformat()
                },
                "user_context": {
                    "is_global_admin": self.is_global_admin,
                    "accessible_countries_count": 0
                }
            }
