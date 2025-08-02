from django.db.models import Sum, Count, Q, Max
from django.core.exceptions import ValidationError
from core.models import Client, Claim, Invoice, InsuredEmployer, Policy, Insured, Partner, Act, ActFamily
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

