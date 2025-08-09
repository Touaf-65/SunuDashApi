from django.db.models import Sum, Count, Q, Max
from django.core.exceptions import ValidationError
from core.models import Client, Claim, Invoice, InsuredEmployer, Policy, Insured, Partner, Act, ActFamily
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    compute_evolution_rate, format_series_for_multi_line_chart,
    format_top_clients_series, to_date
)
import logging
import json
import math

def sanitize_float(value):
    """Sanitize float values to ensure JSON serialization compatibility."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return 0.0  # Replace NaN/inf with 0
        return round(value, 2)  # Round to 2 decimal places
    elif isinstance(value, dict):
        return {key: sanitize_float(val) for key, val in value.items()}
    elif isinstance(value, list):
        return [sanitize_float(val) for val in value]
    else:
        return value

logger = logging.getLogger(__name__)


class ClientPolicyStatisticsService:
    """
    Service to generate statistics for a specific policy of a client over a given period.
    """
    
    def __init__(self, policy_id, date_start_str, date_end_str):
        """
        Initializes the service with the basic parameters.
        
        Args:
            policy_id (int): Policy ID
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.policy_id = int(policy_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientPolicyStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_filters(self):
        """
        Configures the base filters for queries with optimized querysets.
        """
        try:
            # Base policy queryset with select_related
            self.policy = Policy.objects.select_related('client', 'client__country').filter(
                id=self.policy_id
            ).first()
            
            # Validate that policy exists
            if not self.policy:
                logger.warning(f"No policy found for policy_id: {self.policy_id}")
                raise ValidationError(f"Policy with ID {self.policy_id} does not exist")
            
            # Get client information
            self.client = self.policy.client
            self.client_id = self.client.id
            
            # Base claims queryset for this policy
            self.claims = Claim.objects.select_related(
                'invoice', 'policy__client', 'insured', 'partner', 'act__family'
            ).filter(
                policy_id=self.policy_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Generate all periods for the date range
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
            
            # Standard logging for monitoring
            logger.info(f"Policy {self.policy_id}: {self.claims.count()} claims")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_consumption_series(self):
        """
        Gets consumption series in the format [[timestamp, value], ...]
        
        Returns:
            list: Time series of reimbursed amounts as [timestamp, value] pairs
        """
        try:
            claims_data = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            
            # Create a map for quick lookup
            claims_map = {c['period']: float(c['total'] or 0) for c in claims_data}
            
            # Fill all periods with data
            consumption_series = []
            for period in self.periods:
                timestamp = int(period.timestamp()) * 1000
                value = claims_map.get(period, 0)
                consumption_series.append([timestamp, value])
            
            return consumption_series
        except Exception as e:
            logger.error(f"Error in get_consumption_series: {e}")
            return []
    
    def get_nb_primary_series(self):
        """
        Gets number of primary insured series in the format [[timestamp, value], ...]
        
        Returns:
            list: Time series of primary insured count as [timestamp, value] pairs
        """
        try:
            nb_primary_series = []
            for period in self.periods:
                nb_primary = InsuredEmployer.objects.filter(
                    policy_id=self.policy_id,
                    role='primary'
                ).filter(
                    Q(start_date__lte=period) | Q(start_date__isnull=True)
                ).filter(
                    Q(end_date__gt=period) | Q(end_date__isnull=True)
                ).count()
                
                timestamp = int(period.timestamp()) * 1000
                nb_primary_series.append([timestamp, nb_primary])
            
            return nb_primary_series
        except Exception as e:
            logger.error(f"Error in get_nb_primary_series: {e}")
            return []
    
    def get_nb_total_series(self):
        """
        Gets number of total insured series in the format [[timestamp, value], ...]
        
        Returns:
            list: Time series of total insured count as [timestamp, value] pairs
        """
        try:
            nb_total_series = []
            for period in self.periods:
                nb_total = InsuredEmployer.objects.filter(
                    policy_id=self.policy_id
                ).filter(
                    Q(start_date__lte=period) | Q(start_date__isnull=True)
                ).filter(
                    Q(end_date__gt=period) | Q(end_date__isnull=True)
                ).count()
                
                timestamp = int(period.timestamp()) * 1000
                nb_total_series.append([timestamp, nb_total])
            
            return nb_total_series
        except Exception as e:
            logger.error(f"Error in get_nb_total_series: {e}")
            return []
    
    def generate_statistics(self):
        """
        Generates comprehensive statistics for the policy in the exact format expected by the view.
        
        Returns:
            dict: Complete statistics matching the original view format
        """
        try:
            # Get basic series
            consumption_series = self.get_consumption_series()
            nb_primary_series = self.get_nb_primary_series()
            nb_total_series = self.get_nb_total_series()
            
            # Calculate evolution rates and actual values
            consumption_evolution_rate = self._compute_evolution_rate(consumption_series)
            actual_consumption_value = self._get_actual_value(consumption_series)
            
            nb_primary_evolution_rate = self._compute_evolution_rate(nb_primary_series)
            actual_nb_primary_value = self._get_actual_value(nb_primary_series)
            
            nb_total_evolution_rate = self._compute_evolution_rate(nb_total_series)
            actual_nb_total_value = self._get_actual_value(nb_total_series)
            
            # Get complex series
            nb_assures_par_type_series = self._get_nb_assures_par_type_series()
            top5_familles_conso_series, top5_familles_labels = self._get_top5_familles_conso_series()
            top5_categories_actes_series, top5_categories_labels = self._get_top5_categories_actes_series()
            top5_partners_conso_series, top5_partners_labels, top_partners_table = self._get_top5_partners_conso_series()
            
            # Get policy info
            policy_number = self.policy.policy_number
            consommation_percentages_client_polices = self._get_consommation_percentages_client_polices()
            
            return {
                "granularity": self.granularity,
                "policy_number": policy_number,
                "consommation_percentages_client_polices": consommation_percentages_client_polices,
                "consumption_series": consumption_series,
                "consumption_evolution_rate": consumption_evolution_rate,
                "actual_consumption_value": actual_consumption_value,
                "nb_primary_series": nb_primary_series,
                "nb_primary_evolution_rate": nb_primary_evolution_rate,
                "actual_nb_primary_value": actual_nb_primary_value,
                "nb_total_series": nb_total_series,
                "nb_total_evolution_rate": nb_total_evolution_rate,
                "actual_nb_total_value": actual_nb_total_value,
                "nb_assures_par_type_series": nb_assures_par_type_series,
                "top5_familles_conso_series": top5_familles_conso_series,
                "top5_familles_labels": top5_familles_labels,
                "top5_categories_actes_series": top5_categories_actes_series,
                "top5_categories_labels": top5_categories_labels,
                "top5_partners_conso_series": top5_partners_conso_series,
                "top5_partners_labels": top5_partners_labels,
                "top_partners_table": top_partners_table
            }
            
        except Exception as e:
            logger.error(f"Error generating policy statistics: {e}")
            return {}
    
    def _get_nb_assures_par_type_series(self):
        """
        Gets insured by type series in the format expected by the view
        
        Returns:
            list: Series data with name and data for each role type
        """
        try:
            role_map = {
                'primary': 'Assurés Principaux',
                'spouse': 'Assurés conjoints',
                'child': 'Assurés enfants',
                'other': 'Autres assurés'
            }
            roles = ['primary', 'spouse', 'child', 'other']
            nb_assures_par_type_series = []
            
            for role in roles:
                data = []
                for period in self.periods:
                    if role == 'other':
                        count = InsuredEmployer.objects.filter(
                            policy_id=self.policy_id
                        ).exclude(role__in=['primary','spouse','child'])\
                         .filter(Q(start_date__lte=period) | Q(start_date__isnull=True))\
                         .filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                    else:
                        count = InsuredEmployer.objects.filter(
                            policy_id=self.policy_id,
                            role=role
                        ).filter(Q(start_date__lte=period) | Q(start_date__isnull=True))\
                         .filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                    
                    date_label = self._get_date_label(period)
                    data.append({"x": date_label, "y": count})
                
                nb_assures_par_type_series.append({
                    "name": role_map[role],
                    "data": data
                })
            
            return nb_assures_par_type_series
        except Exception as e:
            logger.error(f"Error in _get_nb_assures_par_type_series: {e}")
            return []
    
    def _get_top5_familles_conso_series(self):
        """
        Gets top 5 families consumption series
        
        Returns:
            tuple: (series_data, labels)
        """
        try:
            # Get top 5 families by consumption
            principals = InsuredEmployer.objects.filter(policy_id=self.policy_id, role='primary')
            family_consumptions = []
            
            for principal in principals:
                family_ids = [principal.insured_id] + list(
                    InsuredEmployer.objects.filter(
                        policy_id=self.policy_id,
                        primary_insured_ref=principal.insured_id
                    ).values_list('insured_id', flat=True)
                )
                
                total = Claim.objects.filter(
                    policy_id=self.policy_id,
                    insured_id__in=family_ids,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
                
                family_consumptions.append({
                    'principal': principal.insured.name,
                    'family_ids': family_ids,
                    'total': float(total)
                })
            
            top_families = sorted(family_consumptions, key=lambda x: x['total'], reverse=True)[:5]
            
            # Generate series data
            top5_familles_conso_series = []
            for fam in top_families:
                claims_data = list(
                    Claim.objects.filter(
                        policy_id=self.policy_id,
                        insured_id__in=fam['family_ids'],
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False
                    )
                    .annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: float(c['total'] or 0) for c in claims_data}
                data = [claims_map.get(period, 0) for period in self.periods]
                
                top5_familles_conso_series.append({
                    "name": fam['principal'],
                    "data": data
                })
            
            top5_familles_labels = [self._get_date_label(period) for period in self.periods]
            
            return top5_familles_conso_series, top5_familles_labels
        except Exception as e:
            logger.error(f"Error in _get_top5_familles_conso_series: {e}")
            return [], []
    
    def _get_top5_categories_actes_series(self):
        """
        Gets top 5 act categories consumption series
        
        Returns:
            tuple: (series_data, labels)
        """
        try:
            # Get top 5 acts by consumption
            acts = list(
                self.claims.filter(act__isnull=False)
                .values('act__label')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('-total')[:5]
            )
            
            act_names = [a['act__label'] for a in acts]
            top5_categories_actes_series = []
            
            for aname in act_names:
                claims_data = list(
                    self.claims.filter(act__label=aname)
                    .annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: float(c['total'] or 0) for c in claims_data}
                data = [claims_map.get(period, 0) for period in self.periods]
                
                top5_categories_actes_series.append({
                    "name": aname,
                    "data": data
                })
            
            top5_categories_labels = [self._get_date_label(period) for period in self.periods]
            
            return top5_categories_actes_series, top5_categories_labels
        except Exception as e:
            logger.error(f"Error in _get_top5_categories_actes_series: {e}")
            return [], []
    
    def _get_top5_partners_conso_series(self):
        """
        Gets top 5 partners consumption series
        
        Returns:
            tuple: (series_data, labels, table_data)
        """
        try:
            # Get top 5 partners by consumption
            partners = list(
                self.claims.filter(partner__isnull=False)
                .values('partner', 'partner__name')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('-total')[:5]
            )
            
            partner_tuples = [(p['partner'], p['partner__name']) for p in partners] if partners else []
            partner_consumption_series = []
            
            for partner_id, pname in partner_tuples:
                claims_data = list(
                    self.claims.filter(partner_id=partner_id)
                    .annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: float(c['total'] or 0) for c in claims_data}
                data = [claims_map.get(period, 0) for period in self.periods]
                
                partner_consumption_series.append({
                    "name": pname,
                    "data": data
                })
            
            # Generate table data
            top_partners_table = []
            for partner_id, pname in partner_tuples:
                agg = self.claims.filter(partner_id=partner_id).aggregate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount')
                )
                top_partners_table.append({
                    "id": partner_id,
                    "name": pname,
                    "claimed": float(agg['total_claimed'] or 0),
                    "reimbursed": float(agg['total_reimbursed'] or 0)
                })
            
            top5_partners_labels = [self._get_date_label(period) for period in self.periods]
            
            return partner_consumption_series, top5_partners_labels, top_partners_table
        except Exception as e:
            logger.error(f"Error in _get_top5_partners_conso_series: {e}")
            return [], [], []
    
    def _get_consommation_percentages_client_polices(self):
        """
        Gets consumption percentages between this policy and other client policies
        
        Returns:
            list: [policy_percentage, other_policies_percentage]
        """
        try:
            client_id = self.client_id
            
            # Policy consumption
            policy_conso = self.claims.aggregate(
                total=Sum('invoice__reimbursed_amount')
            )['total'] or 0
            
            # Total client consumption (all policies)
            client_conso = Claim.objects.filter(
                policy__client_id=client_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
            
            # Other policies consumption
            autres_conso = client_conso - policy_conso
            
            if client_conso > 0:
                return [
                    round(100 * policy_conso / client_conso, 2),
                    round(100 * autres_conso / client_conso, 2)
                ]
            else:
                return [0, 0]
        except Exception as e:
            logger.error(f"Error in _get_consommation_percentages_client_polices: {e}")
            return [0, 0]
    
    def _get_date_label(self, dt):
        """
        Get date label based on granularity
        
        Args:
            dt: datetime object
        
        Returns:
            str: Formatted date label
        """
        if self.granularity == 'day':
            return dt.strftime('%Y-%m-%d')
        elif self.granularity == 'month':
            return dt.strftime('%Y-%m')
        elif self.granularity == 'year':
            return dt.strftime('%Y')
        elif self.granularity == 'quarter':
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        return str(dt)
    
    def _compute_evolution_rate(self, series):
        """
        Compute evolution rate for a series
        
        Args:
            series: List of [timestamp, value] pairs
        
        Returns:
            float or str: Evolution rate or "Nouveau"
        """
        if not series or len(series) == 0:
            return 0.0
        if len(series) == 1:
            first = last = float(series[0][1] if isinstance(series[0], (list, tuple)) else series[0]['y'] or 0)
        else:
            first = float(series[0][1] if isinstance(series[0], (list, tuple)) else series[0]['y'] or 0)
            last = float(series[-1][1] if isinstance(series[-1], (list, tuple)) else series[-1]['y'] or 0)
        
        if first == 0:
            if last == 0:
                return 0.0
            else:
                return "Nouveau"
        return round(100 * (last - first) / abs(first), 2)
    
    def _get_actual_value(self, series):
        """
        Get actual (last) value from a series
        
        Args:
            series: List of [timestamp, value] pairs
        
        Returns:
            float: Last value in the series
        """
        if not series:
            return 0
        return float(series[-1][1] if isinstance(series[-1], (list, tuple)) else series[-1]['y'] or 0)
    
    def generate_statistics(self):
        """
        Generates comprehensive statistics for the policy in the exact format expected by the view.
        
        Returns:
            dict: Complete statistics matching the original view format
        """
        try:
            # Get basic series
            consumption_series = self.get_consumption_series()
            nb_primary_series = self.get_nb_primary_series()
            nb_total_series = self.get_nb_total_series()
            
            # Calculate evolution rates and actual values
            consumption_evolution_rate = self._compute_evolution_rate(consumption_series)
            actual_consumption_value = self._get_actual_value(consumption_series)
            
            nb_primary_evolution_rate = self._compute_evolution_rate(nb_primary_series)
            actual_nb_primary_value = self._get_actual_value(nb_primary_series)
            
            nb_total_evolution_rate = self._compute_evolution_rate(nb_total_series)
            actual_nb_total_value = self._get_actual_value(nb_total_series)
            
            # Get complex series
            nb_assures_par_type_series = self._get_nb_assures_par_type_series()
            top5_familles_conso_series, top5_familles_labels = self._get_top5_familles_conso_series()
            top5_categories_actes_series, top5_categories_labels = self._get_top5_categories_actes_series()
            top5_partners_conso_series, top5_partners_labels, top_partners_table = self._get_top5_partners_conso_series()
            
            # Get policy info
            policy_number = self.policy.policy_number
            consommation_percentages_client_polices = self._get_consommation_percentages_client_polices()
            
            return {
                "granularity": self.granularity,
                "policy_number": policy_number,
                "consommation_percentages_client_polices": consommation_percentages_client_polices,
                "consumption_series": consumption_series,
                "consumption_evolution_rate": consumption_evolution_rate,
                "actual_consumption_value": actual_consumption_value,
                "nb_primary_series": nb_primary_series,
                "nb_primary_evolution_rate": nb_primary_evolution_rate,
                "actual_nb_primary_value": actual_nb_primary_value,
                "nb_total_series": nb_total_series,
                "nb_total_evolution_rate": nb_total_evolution_rate,
                "actual_nb_total_value": actual_nb_total_value,
                "nb_assures_par_type_series": nb_assures_par_type_series,
                "top5_familles_conso_series": top5_familles_conso_series,
                "top5_familles_labels": top5_familles_labels,
                "top5_categories_actes_series": top5_categories_actes_series,
                "top5_categories_labels": top5_categories_labels,
                "top5_partners_conso_series": top5_partners_conso_series,
                "top5_partners_labels": top5_partners_labels,
                "top_partners_table": top_partners_table
            }
            
        except Exception as e:
            logger.error(f"Error generating policy statistics: {e}")
            return {}



class ClientPolicyListService:
    """
    Service to generate statistics for all policies of a specific client over a given period.
    """
    
    def __init__(self, client_id, date_start_str, date_end_str):
        """
        Initialize the service with client ID and date range.
        
        Args:
            client_id (int): ID of the client
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.client_id = int(client_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientPolicyListStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_filters(self):
        """
        Set up base querysets for client, policies and related data.
        """
        try:
            # Get client
            self.client = Client.objects.select_related('country').filter(
                id=self.client_id
            ).first()
            
            if not self.client:
                logger.warning(f"No client found for client_id: {self.client_id}")
                raise ValidationError(f"Client with ID {self.client_id} does not exist")
            
            # Get all policies for this client
            self.policies = Policy.objects.select_related('client').filter(
                client_id=self.client_id
            )
            
            # Get all insured IDs for this client
            self.insured_ids = list(
                InsuredEmployer.objects.filter(employer_id=self.client_id)
                .values_list('insured_id', flat=True)
            )
            
            # Generate periods for time series alignment
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
            
            logger.info(f"Client {self.client_id}: {self.policies.count()} policies, {len(self.insured_ids)} insured")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def _get_role_consumption_share(self):
        """
        Calculate consumption share by insured role across all policies.
        
        Returns:
            list: Consumption amounts for [primary, spouse, child]
        """
        try:
            claims_by_role = (
                Claim.objects.filter(
                    insured_id__in=self.insured_ids,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                )
                .values('insured__insured_clients__role')
                .annotate(total=Sum('invoice__reimbursed_amount'))
            )
            
            role_totals = {'primary': 0, 'spouse': 0, 'child': 0}
            for claim in claims_by_role:
                role = claim['insured__insured_clients__role']
                value = sanitize_float(claim['total'] or 0)
                if role in role_totals:
                    role_totals[role] = value
            
            return [
                role_totals['primary'],
                role_totals['spouse'],
                role_totals['child']
            ]
        except Exception as e:
            logger.error(f"Error in _get_role_consumption_share: {e}")
            return [0, 0, 0]
    
    def _get_policy_consumption_series(self):
        """
        Generate consumption time series for each policy.
        
        Returns:
            list: List of series data for each policy
        """
        try:
            policy_consumption_series = []
            
            for policy in self.policies:
                # Get claims data for this policy
                claims_data = list(
                    Claim.objects.filter(
                        policy_id=policy.id,
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False
                    )
                    .annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                # Create a map for quick lookup
                claims_map = {c['period']: sanitize_float(c['total'] or 0) for c in claims_data}
                
                # Fill all periods with data
                data = [claims_map.get(period, 0) for period in self.periods]
                
                serie = {
                    "name": policy.policy_number,
                    "data": data
                }
                policy_consumption_series.append(serie)
            
            return policy_consumption_series
        except Exception as e:
            logger.error(f"Error in _get_policy_consumption_series: {e}")
            return []
    
    def _get_policies_table(self):
        """
        Generate table data for all policies.
        
        Returns:
            list: List of policy statistics dictionaries
        """
        try:
            policies_table = []
            
            for policy in self.policies:
                # Get insured links for this policy
                insured_links = InsuredEmployer.objects.filter(policy_id=policy.id)
                nb_primary = insured_links.filter(role='primary').count()
                nb_total = insured_links.count()
                
                # Get insured IDs for this policy
                policy_insured_ids = list(insured_links.values_list('insured_id', flat=True))
                
                # Calculate aggregated amounts
                agg = Claim.objects.filter(
                    policy_id=policy.id,
                    insured_id__in=policy_insured_ids,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                ).aggregate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount')
                )
                
                policies_table.append({
                    "policy_id": policy.id,
                    "policy_number": policy.policy_number,
                    "nb_primary": nb_primary,
                    "nb_total": nb_total,
                    "consumption": sanitize_float(agg['total_reimbursed'] or 0),
                    "claimed": sanitize_float(agg['total_claimed'] or 0),
                })
            
            return policies_table
        except Exception as e:
            logger.error(f"Error in _get_policies_table: {e}")
            return []
    
    def _get_consistency_warning(self, role_consumption_share, policies_table):
        """
        Check for consistency between role consumption and policy consumption.
        
        Args:
            role_consumption_share (list): Consumption by role
            policies_table (list): Policies table data
            
        Returns:
            dict or None: Consistency warning if applicable
        """
        try:
            if len(policies_table) == 1:
                total_role = sum(role_consumption_share)
                policy_total = policies_table[0]["consumption"]
                
                if abs(total_role - policy_total) > 1e-2:  # floating point tolerance
                    return {
                        "sum_role_consumption_share": total_role,
                        "policy_consumption": policy_total,
                        "diff": total_role - policy_total,
                        "message": "Incohérence détectée : la somme des consommations par type ne correspond pas à la consommation totale de la police."
                    }
            return None
        except Exception as e:
            logger.error(f"Error in _get_consistency_warning: {e}")
            return None
    
    def _get_date_label(self, dt):
        """
        Generate date label based on granularity.
        
        Args:
            dt (datetime): Date to format
            
        Returns:
            str: Formatted date label
        """
        if self.granularity == 'day':
            return dt.strftime('%Y-%m-%d')
        elif self.granularity == 'month':
            return dt.strftime('%Y-%m')
        elif self.granularity == 'year':
            return dt.strftime('%Y')
        elif self.granularity == 'quarter':
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        return str(dt)
    
    def get_policies_statistics(self):
        """
        Generate comprehensive statistics for all policies of the client.
        
        Returns:
            dict: Complete statistics for client policies
        """
        try:
            # Get role consumption share
            role_consumption_share = self._get_role_consumption_share()
            
            # Get policy consumption series
            policy_consumption_series = self._get_policy_consumption_series()
            
            # Generate period labels for series
            policy_consumption_series_labels = [self._get_date_label(period) for period in self.periods]
            
            # Get policies table
            policies_table = self._get_policies_table()
            
            # Check for consistency warnings
            consistency_warning = self._get_consistency_warning(role_consumption_share, policies_table)
            
            # Compile response data
            response_data = {
                "client_id": self.client.id,
                "client_name": self.client.name,
                "granularity": self.granularity,
                "role_consumption_share": role_consumption_share,
                "policy_consumption_series": policy_consumption_series,
                "policy_consumption_series_labels": policy_consumption_series_labels,
                "policies_table": policies_table,
            }
            
            if consistency_warning:
                response_data["consistency_warning"] = consistency_warning
            
            return sanitize_float(response_data)
            
        except Exception as e:
            logger.error(f"Error generating policies statistics: {e}")
            return {}



class CountryPolicyListService:
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
            logger.error(f"Invalid parameters for CountryPolicyListService: {e}")
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
            
            # Sort by total claimed amount descending (within financial_statistics)
            results.sort(
                key=lambda x: x.get('financial_statistics', {}).get('total_claimed_amount', 0.0),
                reverse=True
            )
            
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
            # Use a queryset-based computation to avoid empty list issues when stats exist
            policies_qs = self.policies
            if not policies_qs.exists():
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



class GlobalPolicyListService:
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
            logger.error(f"Invalid parameters for GlobalPolicyListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_user_permissions(self):
        """
        Setup user permissions - validates that user is global admin.
        """
        try:
            self.is_global_admin = self.user.is_admin_global() 
            
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
            results.sort(key=lambda x: x['financial_statistics']['total_claimed_amount'], reverse=True)
            
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
            

            print(f'#### Policies number: {len(policies_list)}')
            
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
            
            total_policies = self.policies.count()
            unique_clients = self.policies.values('client_id').distinct().count()
            unique_countries = self.policies.values('client__country_id').distinct().count()

            # Aggregate totals directly from DB for accuracy and performance
            insured_links = InsuredEmployer.objects.filter(employer_id__in=self.policies.values('client_id'))
            total_insured = insured_links.values('insured_id').distinct().count()

            claims_qs = Claim.objects.select_related('invoice').filter(
                Q(policy_id__in=self.policies.values('id')) |
                Q(insured__insured_clients__employer_id__in=self.policies.values('client_id'))
            )
            if self.date_start and self.date_end:
                claims_qs = claims_qs.filter(settlement_date__range=(self.date_start, self.date_end))

            amounts = claims_qs.aggregate(
                total_claimed=Sum('invoice__claimed_amount'),
                total_reimbursed=Sum('invoice__reimbursed_amount'),
                nb_claims=Count('id')
            )
            total_claimed = float(amounts['total_claimed'] or 0.0)
            total_reimbursed = float(amounts['total_reimbursed'] or 0.0)
            total_claims = int(amounts['nb_claims'] or 0)
            
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
                "accessible_countries_count": len(self.accessible_country_ids),
                "policies_count": self.policies.count()
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



class GlobalPolicyStatisticsService:
    """
    Service to generate global policy statistics across all countries.
    
    This service provides total counts for all policies, clients, insured, and claims
    across all countries without any geographical restrictions.
    """
    
    def __init__(self, date_start_str, date_end_str):
        """
        Initialize the service with date range.
        
        Args:
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_base_querysets()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for GlobalPolicyStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_querysets(self):
        """
        Set up base querysets for global statistics.
        """
        try:
            # Base querysets for all data
            self.clients = Client.objects.all()
            self.policies = Policy.objects.all()
            self.insured_employers = InsuredEmployer.objects.all()
            self.claims = Claim.objects.all()
            
            # Apply date filters if specified
            if self.date_start and self.date_end:
                self.clients = self.clients.filter(
                    creation_date__range=(self.date_start, self.date_end)
                )
                self.policies = self.policies.filter(
                    creation_date__range=(self.date_start, self.date_end)
                )
                self.insured_employers = self.insured_employers.filter(
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                self.claims = self.claims.filter(
                    settlement_date__range=(self.date_start, self.date_end)
                )
            
            logger.info(f"Global statistics: {self.clients.count()} clients, {self.policies.count()} policies")
            
        except Exception as e:
            logger.error(f"Error setting up base querysets: {e}")
            raise ValidationError(f"Error setting up querysets: {e}")
    
    def get_total_clients_count(self):
        """
        Get the total number of clients across all countries.
        
        Returns:
            int: Total number of clients
        """
        try:
            return self.clients.count()
        except Exception as e:
            logger.error(f"Error getting total clients count: {e}")
            return 0
    
    def get_total_policies_count(self):
        """
        Get the total number of policies across all countries.
        
        Returns:
            int: Total number of policies
        """
        try:
            return self.policies.count()
        except Exception as e:
            logger.error(f"Error getting total policies count: {e}")
            return 0
    
    def get_total_insured_count(self):
        """
        Get the total number of insured individuals across all countries.
        
        Returns:
            int: Total number of insured individuals
        """
        try:
            return self.insured_employers.values('insured').distinct().count()
        except Exception as e:
            logger.error(f"Error getting total insured count: {e}")
            return 0
    
    def get_total_claims_count(self):
        """
        Get the total number of claims across all countries.
        
        Returns:
            int: Total number of claims
        """
        try:
            return self.claims.count()
        except Exception as e:
            logger.error(f"Error getting total claims count: {e}")
            return 0
    
    def get_complete_statistics(self):
        """
        Get complete global policy statistics.
        
        Returns:
            dict: Complete statistics dictionary
        """
        try:
            return {
                "total_clients": self.get_total_clients_count(),
                "total_policies": self.get_total_policies_count(),
                "total_insured": self.get_total_insured_count(),
                "total_claims": self.get_total_claims_count(),
                "date_range": {
                    "start": self.date_start.isoformat() if self.date_start else None,
                    "end": self.date_end.isoformat() if self.date_end else None
                },
                "scope": "global"
            }
        except Exception as e:
            logger.error(f"Error getting complete statistics: {e}")
            return {
                "total_clients": 0,
                "total_policies": 0,
                "total_insured": 0,
                "total_claims": 0,
                "date_range": {
                    "start": self.date_start.isoformat() if self.date_start else None,
                    "end": self.date_end.isoformat() if self.date_end else None
                },
                "scope": "global"
            }


class CountryPolicyStatisticsService:
    """
    Service to generate country-specific policy statistics.
    
    This service provides total counts for policies, clients, insured, and claims
    for a specific country with territorial access restrictions.
    """
    
    def __init__(self, country_id, date_start_str, date_end_str):
        """
        Initialize the service with country ID and date range.
        
        Args:
            country_id (int): Country ID
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.country_id = int(country_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_base_querysets()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryPolicyStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_querysets(self):
        """
        Set up base querysets for country-specific statistics.
        """
        try:
            # Validate that country exists
            self.country = Country.objects.filter(id=self.country_id).first()
            if not self.country:
                logger.warning(f"No country found for country_id: {self.country_id}")
                raise ValidationError(f"Country with ID {self.country_id} does not exist")
            
            # Base querysets for country-specific data
            self.clients = Client.objects.filter(country_id=self.country_id)
            self.policies = Policy.objects.filter(client__country_id=self.country_id)
            self.insured_employers = InsuredEmployer.objects.filter(employer__country_id=self.country_id)
            self.claims = Claim.objects.filter(policy__client__country_id=self.country_id)
            
            # Apply date filters if specified
            if self.date_start and self.date_end:
                self.clients = self.clients.filter(
                    creation_date__range=(self.date_start, self.date_end)
                )
                self.policies = self.policies.filter(
                    creation_date__range=(self.date_start, self.date_end)
                )
                self.insured_employers = self.insured_employers.filter(
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                self.claims = self.claims.filter(
                    settlement_date__range=(self.date_start, self.date_end)
                )
            
            logger.info(f"Country {self.country_id} statistics: {self.clients.count()} clients, {self.policies.count()} policies")
            
        except Exception as e:
            logger.error(f"Error setting up base querysets: {e}")
            raise ValidationError(f"Error setting up querysets: {e}")
    
    def get_total_clients_count(self):
        """
        Get the total number of clients in the specific country.
        
        Returns:
            int: Total number of clients in the country
        """
        try:
            return self.clients.count()
        except Exception as e:
            logger.error(f"Error getting total clients count: {e}")
            return 0
    
    def get_total_policies_count(self):
        """
        Get the total number of policies in the specific country.
        
        Returns:
            int: Total number of policies in the country
        """
        try:
            return self.policies.count()
        except Exception as e:
            logger.error(f"Error getting total policies count: {e}")
            return 0
    
    def get_total_insured_count(self):
        """
        Get the total number of insured individuals in the specific country.
        
        Returns:
            int: Total number of insured individuals in the country
        """
        try:
            return self.insured_employers.values('insured').distinct().count()
        except Exception as e:
            logger.error(f"Error getting total insured count: {e}")
            return 0
    
    def get_total_claims_count(self):
        """
        Get the total number of claims in the specific country.
        
        Returns:
            int: Total number of claims in the country
        """
        try:
            return self.claims.count()
        except Exception as e:
            logger.error(f"Error getting total claims count: {e}")
            return 0
    
    def get_complete_statistics(self):
        """
        Get complete country-specific policy statistics.
        
        Returns:
            dict: Complete statistics dictionary
        """
        try:
            return {
                "total_clients": self.get_total_clients_count(),
                "total_policies": self.get_total_policies_count(),
                "total_insured": self.get_total_insured_count(),
                "total_claims": self.get_total_claims_count(),
                "country": {
                    "id": self.country.id,
                    "name": self.country.name,
                    "code": getattr(self.country, 'code', '')
                },
                "date_range": {
                    "start": self.date_start.isoformat() if self.date_start else None,
                    "end": self.date_end.isoformat() if self.date_end else None
                },
                "scope": "country"
            }
        except Exception as e:
            logger.error(f"Error getting complete statistics: {e}")
            return {
                "total_clients": 0,
                "total_policies": 0,
                "total_insured": 0,
                "total_claims": 0,
                "country": {
                    "id": self.country_id,
                    "name": "Unknown",
                    "code": ""
                },
                "date_range": {
                    "start": self.date_start.isoformat() if self.date_start else None,
                    "end": self.date_end.isoformat() if self.date_end else None
                },
                "scope": "country"
            }


