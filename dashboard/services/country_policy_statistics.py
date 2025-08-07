from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError
from core.models import Policy, Client, Claim, Invoice, InsuredEmployer
from countries.models import Country
from .base import parse_date_range, sanitize_float
import logging

logger = logging.getLogger(__name__)


class CountryPolicyListService:
    """
    Service to retrieve a list of all policies in a country with detailed statistics.
    For each policy, provides: number of insured, client name, total reimbursed amount, total claimed amount.
    """
    
    def __init__(self, country_id, date_start_str, date_end_str):
        """
        Initialize the service with country ID and date range.
        
        Args:
            country_id (int): ID of the country
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.country_id = int(country_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryPolicyListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_filters(self):
        """
        Set up base querysets for policies and related data in the specified country.
        """
        try:
            # Validate that country exists
            self.country = Country.objects.filter(id=self.country_id).first()
            if not self.country:
                logger.warning(f"No country found for country_id: {self.country_id}")
                raise ValidationError(f"Country with ID {self.country_id} does not exist")
            
            # Base policies queryset for the country
            self.policies = Policy.objects.select_related('client', 'client__country').filter(
                client__country_id=self.country_id
            )
            
            # Validate that policies exist
            if not self.policies.exists():
                logger.warning(f"No policies found for country_id: {self.country_id}")
            
            # Standard logging for monitoring
            logger.info(f"Country {self.country_id}: {self.policies.count()} policies found")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_policies_statistics_list(self):
        """
        Generate statistics list for all policies in the country.
        
        Returns:
            list: List of policy statistics dictionaries
        """
        try:
            results = []
            
            for policy in self.policies:
                policy_stats = self._get_policy_statistics(policy)
                results.append(policy_stats)
            
            # Sort by total claimed amount descending
            results.sort(key=lambda x: x['total_claimed_amount'], reverse=True)
            
            # Sanitize all float values to prevent JSON serialization errors
            return sanitize_float(results)
            
        except Exception as e:
            logger.error(f"Error generating policies statistics list: {e}")
            return []
    
    def _get_policy_statistics(self, policy):
        """
        Get statistics for a single policy.
        
        Args:
            policy: Policy object
            
        Returns:
            dict: Policy statistics with insured count, client name, and amounts
        """
        try:
            # Get insured employees for this policy
            insured_links = InsuredEmployer.objects.select_related('insured').filter(
                employer=policy.client
            )
            nb_insured = insured_links.count()
            
            # Get insured IDs for claims filtering
            insured_ids = list(insured_links.values_list('insured_id', flat=True))
            
            # Get claims for this policy in the date range
            # Use both insured and policy relationships like in ClientStatisticsService
            claims = Claim.objects.select_related('invoice').filter(
                Q(insured_id__in=insured_ids) | Q(policy_id=policy.id),
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Calculate consumption and reimbursement totals
            amounts_data = claims.aggregate(
                total_claimed=Sum('invoice__claimed_amount'),
                total_reimbursed=Sum('invoice__reimbursed_amount')
            )
            
            total_claimed_amount = float(amounts_data['total_claimed'] or 0)
            total_reimbursed_amount = float(amounts_data['total_reimbursed'] or 0)
            
            return {
                "policy_id": policy.id,
                "policy_number": policy.policy_number if hasattr(policy, 'policy_number') else f"POL-{policy.id}",
                "client_id": policy.client.id,
                "client_name": policy.client.name,
                "client_contact": policy.client.contact or "",
                "nb_insured": nb_insured,
                "total_claimed_amount": total_claimed_amount,
                "total_reimbursed_amount": total_reimbursed_amount,
                "claims_count": claims.count(),
                "policy_start_date": policy.start_date.isoformat() if hasattr(policy, 'start_date') and policy.start_date else None,
                "policy_end_date": policy.end_date.isoformat() if hasattr(policy, 'end_date') and policy.end_date else None,
                "is_active": getattr(policy, 'is_active', True)
            }
            
        except Exception as e:
            logger.error(f"Error calculating statistics for policy {policy.id}: {e}")
            return {
                "policy_id": policy.id,
                "policy_number": policy.policy_number if hasattr(policy, 'policy_number') else f"POL-{policy.id}",
                "client_id": policy.client.id,
                "client_name": policy.client.name,
                "client_contact": policy.client.contact or "",
                "nb_insured": 0,
                "total_claimed_amount": 0.0,
                "total_reimbursed_amount": 0.0,
                "claims_count": 0,
                "policy_start_date": None,
                "policy_end_date": None,
                "is_active": getattr(policy, 'is_active', True)
            }
    
    def get_policies_statistics_summary(self):
        """
        Get summary statistics for all policies in the country.
        
        Returns:
            dict: Summary statistics
        """
        try:
            policies_list = self.get_policies_statistics_list()
            
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
                    "average_insured_per_policy": 0.0
                }
            
            total_policies = len(policies_list)
            unique_clients = len(set(policy['client_id'] for policy in policies_list))
            total_insured = sum(policy['nb_insured'] for policy in policies_list)
            total_claimed = sum(policy['total_claimed_amount'] for policy in policies_list)
            total_reimbursed = sum(policy['total_reimbursed_amount'] for policy in policies_list)
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
                "average_insured_per_policy": total_insured / total_policies if total_policies > 0 else 0.0,
                "reimbursement_rate": (total_reimbursed / total_claimed * 100) if total_claimed > 0 else 0.0
            })
            
        except Exception as e:
            logger.error(f"Error generating policies statistics summary: {e}")
            return {
                "total_policies": 0,
                "total_clients": 0,
                "total_insured": 0,
                "total_claimed_amount": 0.0,
                "total_reimbursed_amount": 0.0,
                "total_claims": 0,
                "average_claimed_per_policy": 0.0,
                "average_reimbursed_per_policy": 0.0,
                "average_insured_per_policy": 0.0,
                "reimbursement_rate": 0.0
            }
    
    def get_complete_policies_list(self):
        """
        Get complete policies list with summary statistics.
        
        Returns:
            dict: Complete policies data with summary
        """
        try:
            policies_list = self.get_policies_statistics_list()
            summary = self.get_policies_statistics_summary()
            
            return {
                "policies_list": policies_list,
                "summary": summary,
                "country": {
                    "id": self.country.id,
                    "name": self.country.name
                },
                "date_range": {
                    "start": self.date_start.isoformat(),
                    "end": self.date_end.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating complete policies list: {e}")
            return {
                "policies_list": [],
                "summary": self.get_policies_statistics_summary(),
                "country": {
                    "id": self.country_id,
                    "name": "Unknown"
                },
                "date_range": {
                    "start": self.date_start.isoformat(),
                    "end": self.date_end.isoformat()
                }
            }
