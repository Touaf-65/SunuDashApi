from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError
from core.models import Policy, Client, Claim, Invoice, InsuredEmployer
from countries.models import Country
from users.models import CustomUser
from .base import parse_date_range, sanitize_float
import logging

logger = logging.getLogger(__name__)


class TerritorialAdminPolicyListService:
    """
    Service to retrieve and filter policies for Territorial Administrators only.
    
    Features:
    - Access only to policies from the admin's assigned country
    - Filter by client (searchfield on clients from their country)
    - Complete statistics for each policy
    - No country selection (automatically restricted to admin's country)
    """
    
    def __init__(self, user, date_start_str, date_end_str, client_id=None):
        """
        Initialize the service with user context and filters.
        
        Args:
            user: Current user (CustomUser instance) - must be territorial admin
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
            client_id (int, optional): Filter by client ID
        """
        try:
            self.user = user
            self.client_id = int(client_id) if client_id else None
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_user_permissions()
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for TerritorialAdminPolicyListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_user_permissions(self):
        """
        Setup user permissions - validates that user is territorial admin and gets their country.
        """
        try:
            self.is_territorial_admin = (
                hasattr(self.user, 'is_territorial_admin') and 
                getattr(self.user, 'is_territorial_admin', False)
            ) or (
                not self.user.is_superuser and 
                not getattr(self.user, 'is_global_admin', False)
            )
            
            if not self.is_territorial_admin:
                raise ValidationError("Ce service est réservé aux administrateurs territoriaux uniquement.")
            
            # Get the territorial admin's assigned country
            if hasattr(self.user, 'country') and self.user.country:
                self.assigned_country = self.user.country
                self.country_id = self.assigned_country.id
                logger.info(f"Territorial admin {self.user.email} - Access to country {self.assigned_country.name}")
            else:
                raise ValidationError("Aucun pays n'est assigné à cet administrateur territorial.")
            
        except Exception as e:
            logger.error(f"Error setting up user permissions: {e}")
            raise ValidationError(f"Error setting up permissions: {e}")
    
    def _setup_base_filters(self):
        """
        Set up base querysets for policies - territorial admin sees only policies from their country.
        """
        try:
            # Start with policies from the admin's assigned country only
            policies_query = Policy.objects.select_related('client', 'client__country').filter(
                client__country_id=self.country_id
            )
            
            # Apply client filter if specified
            if self.client_id:
                # Verify that the client belongs to the admin's country
                client_exists = Client.objects.filter(
                    id=self.client_id, 
                    country_id=self.country_id
                ).exists()
                
                if not client_exists:
                    raise ValidationError("Ce client n'appartient pas à votre pays assigné.")
                
                policies_query = policies_query.filter(client_id=self.client_id)
            
            self.policies = policies_query
            
            logger.info(f"Territorial admin {self.user.email}: {self.policies.count()} policies found in {self.assigned_country.name}")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_available_clients(self):
        """
        Get list of clients available for filtering (only from admin's country).
        
        Returns:
            list: List of client dictionaries from the admin's country
        """
        try:
            clients_query = Client.objects.select_related('country').filter(
                country_id=self.country_id
            )
            
            clients = []
            for client in clients_query:
                # Count policies for this client
                policy_count = Policy.objects.filter(client_id=client.id).count()
                
                clients.append({
                    "id": client.id,
                    "name": client.name,
                    "contact": client.contact or "",
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
                    "contact": policy.client.contact or ""
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
                    "contact": policy.client.contact or ""
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
            total_insured = sum(policy['insured_statistics']['total_insured'] for policy in policies_list)
            total_claimed = sum(policy['financial_statistics']['total_claimed_amount'] for policy in policies_list)
            total_reimbursed = sum(policy['financial_statistics']['total_reimbursed_amount'] for policy in policies_list)
            total_claims = sum(policy['claims_count'] for policy in policies_list)
            
            return sanitize_float({
                "total_policies": total_policies,
                "total_clients": unique_clients,
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
                    "clients": self.get_available_clients()
                },
                "applied_filters": {
                    "client_id": self.client_id,
                    "date_start": self.date_start.isoformat(),
                    "date_end": self.date_end.isoformat()
                },
                "country_context": {
                    "id": self.assigned_country.id,
                    "name": self.assigned_country.name,
                    "code": getattr(self.assigned_country, 'code', '')
                },
                "user_context": {
                    "is_territorial_admin": True,
                    "assigned_country": self.assigned_country.name
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating complete data: {e}")
            return {
                "policies": [],
                "summary": self.get_summary_statistics(),
                "filter_options": {
                    "clients": []
                },
                "applied_filters": {
                    "client_id": self.client_id,
                    "date_start": self.date_start.isoformat(),
                    "date_end": self.date_end.isoformat()
                },
                "country_context": {
                    "id": self.country_id if hasattr(self, 'country_id') else None,
                    "name": "Unknown",
                    "code": ""
                },
                "user_context": {
                    "is_territorial_admin": True,
                    "assigned_country": "Unknown"
                }
            }
