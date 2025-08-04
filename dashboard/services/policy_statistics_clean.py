##### 1



"""
creons  dans le fichier dashboard/services/partners_statistics.py un service pour les statistiques  sur un partenaire au meme format que ClientStatisticsService dans le fichiers dashboard/services/client_statistics.py, motrant l'evolution du nombre  ses clients, du nombre d'assures ayant consommés, montant rembourses et reclames, part de consommation par type d'assures (par exemple pour un total de 50000; 10000 pour les assures principaux, 20000 pour les spouse, 20000 pour les child)  , un multi line chart pour l'evolution des consommations des 10 clients dont les assures ont le plus consommes chez le partenaire.


"""



import logging
import math
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q, Sum, Count, F
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncYear
from django.utils import timezone

from core.models import (
    Policy, Claim, Invoice, InsuredEmployer, Insured, Partner, Act, ActCategory
)
from .base import get_granularity, parse_date_range

logger = logging.getLogger(__name__)


class ClientPolicyStatisticsService:
    """
    Service for generating comprehensive statistics for a specific policy.
    Follows the same pattern as ClientStatisticsService with proper error handling,
    logging, and optimized queries.
    """
    
    def __init__(self, policy_id, date_start_str, date_end_str):
        """
        Initialize the service with policy ID and date range.
        
        Args:
            policy_id (int): ID of the policy to analyze
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.policy_id = int(policy_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientPolicyStatisticsService: {e}")
            raise ValueError(f"Invalid parameters: {e}")
        self.trunc_function = self._get_trunc_function()
        self.periods = self._generate_periods()
        
        # Get policy information
        try:
            self.policy = Policy.objects.select_related('client').get(pk=policy_id)
            self.client_id = self.policy.client_id
            logger.info(f"Initialized PolicyStatisticsService for policy {policy_id}")
        except Policy.DoesNotExist:
            logger.error(f"Policy {policy_id} not found")
            self.policy = None
            self.client_id = None
    
    def _get_trunc_function(self):
        """Get the appropriate truncation function based on granularity."""
        trunc_map = {
            'day': TruncDay,
            'month': TruncMonth,
            'quarter': TruncQuarter,
            'year': TruncYear
        }
        return trunc_map.get(self.granularity, TruncMonth)
    
    def _generate_periods(self):
        """Generate all periods between start and end dates based on granularity."""
        periods = []
        current = self.date_start
        
        while current <= self.date_end:
            periods.append(current)
            
            if self.granularity == 'day':
                current += timedelta(days=1)
            elif self.granularity == 'month':
                current += relativedelta(months=1)
            elif self.granularity == 'quarter':
                current += relativedelta(months=3)
            else:  # year
                current += relativedelta(years=1)
        
        return periods
    
    @staticmethod
    def sanitize_float(value):
        """Sanitize float values to prevent JSON serialization errors."""
        if value is None or math.isnan(value) or math.isinf(value):
            return 0.0
        return float(value)
    
    def _calculate_evolution_rate(self, series):
        """Calculate evolution rate between first and last values in series."""
        try:
            if not series or len(series) == 0:
                return 0.0
            
            if len(series) == 1:
                return 0.0
            
            first_val = self.sanitize_float(series[0][1] if isinstance(series[0], (list, tuple)) else series[0].get('y', 0))
            last_val = self.sanitize_float(series[-1][1] if isinstance(series[-1], (list, tuple)) else series[-1].get('y', 0))
            
            if first_val == 0:
                return "Nouveau" if last_val > 0 else 0.0
            
            return round(100 * (last_val - first_val) / abs(first_val), 2)
        except Exception as e:
            logger.error(f"Error calculating evolution rate: {e}")
            return 0.0
    
    def _get_actual_value(self, series):
        """Get the maximum value from the series (actual value over period)."""
        try:
            if not series:
                return 0.0
            
            values = []
            for item in series:
                if isinstance(item, (list, tuple)):
                    values.append(self.sanitize_float(item[1]))
                elif isinstance(item, dict):
                    values.append(self.sanitize_float(item.get('y', 0)))
            
            return max(values) if values else 0.0
        except Exception as e:
            logger.error(f"Error getting actual value: {e}")
            return 0.0
    
    def _date_label(self, dt):
        """Format date according to granularity."""
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
    
    def get_consumption_evolution(self):
        """Get consumption evolution over time."""
        try:
            claims = (
                Claim.objects.filter(
                    policy=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                )
                .select_related('invoice')
                .annotate(period=self.trunc_function('settlement_date'))
                .values('period')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            
            # Fill all periods with data
            claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
            series = [[int(period.timestamp()) * 1000, claims_map.get(period, 0.0)] for period in self.periods]
            
            return series
        except Exception as e:
            logger.error(f"Error getting consumption evolution: {e}")
            return []
    
    def get_insured_evolution(self):
        """Get insured employees evolution over time."""
        try:
            # Debug: Check if there are any InsuredEmployer records for this policy
            total_insured_for_policy = InsuredEmployer.objects.filter(policy=self.policy_id).count()
            logger.info(f"DEBUG: Total InsuredEmployer records for policy {self.policy_id}: {total_insured_for_policy}")
            
            if total_insured_for_policy == 0:
                logger.warning(f"DEBUG: No InsuredEmployer records found for policy {self.policy_id}")
                # Let's check if there are any claims for this policy to confirm policy exists
                claims_count = Claim.objects.filter(policy=self.policy_id).count()
                logger.info(f"DEBUG: Claims count for policy {self.policy_id}: {claims_count}")
            
            primary_series = []
            total_series = []
            
            for period in self.periods:
                # Count primary insured at this period
                primary_count = InsuredEmployer.objects.filter(
                    policy=self.policy_id,
                    role='primary',
                    start_date__lte=period
                ).filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                
                # Count total insured at this period
                total_count = InsuredEmployer.objects.filter(
                    policy=self.policy_id,
                    start_date__lte=period
                ).filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                
                ts = int(period.timestamp()) * 1000
                primary_series.append([ts, primary_count])
                total_series.append([ts, total_count])
            
            return {
                'primary': primary_series,
                'total': total_series
            }
        except Exception as e:
            logger.error(f"Error getting insured evolution: {e}")
            return {'primary': [], 'total': []}
    
    def get_insured_by_type_evolution(self):
        """Get insured employees evolution by type (role)."""
        try:
            role_map = {
                'primary': 'Assurés Principaux',
                'spouse': 'Assurés conjoints', 
                'child': 'Assurés enfants',
                'other': 'Autres assurés'
            }
            roles = ['primary', 'spouse', 'child', 'other']
            series = []
            
            for role in roles:
                data = []
                for period in self.periods:
                    if role == 'other':
                        count = InsuredEmployer.objects.filter(
                            policy=self.policy_id,
                            start_date__lte=period
                        ).exclude(role__in=['primary', 'spouse', 'child'])\
                         .filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                    else:
                        count = InsuredEmployer.objects.filter(
                            policy=self.policy_id,
                            role=role,
                            start_date__lte=period
                        ).filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                    
                    data.append({"x": self._date_label(period), "y": count})
                
                series.append({
                    "name": role_map[role],
                    "data": data
                })
            
            return series
        except Exception as e:
            logger.error(f"Error getting insured by type evolution: {e}")
            return []
    
    def get_top_families_consumption(self):
        """Get top 5 families consumption evolution."""
        try:
            principals = InsuredEmployer.objects.filter(
                policy=self.policy_id, 
                role='primary'
            ).select_related('insured')
            
            family_consumptions = []
            for principal in principals:
                # Get family member IDs (principal + beneficiaries)
                family_ids = [principal.insured_id] + list(
                    InsuredEmployer.objects.filter(
                        policy=self.policy_id,
                        primary_insured_ref=principal.insured_id
                    ).values_list('insured_id', flat=True)
                )
                
                # Calculate total consumption for this family
                total = Claim.objects.filter(
                    policy=self.policy_id,
                    insured_id__in=family_ids,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
                
                family_consumptions.append({
                    'principal': principal.insured.name,
                    'family_ids': family_ids,
                    'total': self.sanitize_float(total)
                })
            
            # Get top 5 families
            top_families = sorted(family_consumptions, key=lambda x: x['total'], reverse=True)[:5]
            
            # Generate time series for each family
            series = []
            for fam in top_families:
                claims = (
                    Claim.objects.filter(
                        policy=self.policy_id,
                        insured_id__in=fam['family_ids'],
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False
                    )
                    .select_related('invoice')
                    .annotate(period=self.trunc_function('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
                data = [claims_map.get(period, 0.0) for period in self.periods]
                
                series.append({
                    "name": fam['principal'],
                    "data": data
                })
            
            labels = [self._date_label(period) for period in self.periods]
            return {'series': series, 'labels': labels}
            
        except Exception as e:
            logger.error(f"Error getting top families consumption: {e}")
            return {'series': [], 'labels': []}

    def get_top_acts_consumption(self):
        """Get top 5 acts consumption evolution."""
        try:
            # Get top 5 acts by total consumption
            acts = (
                Claim.objects.filter(
                    policy=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False,
                    act__isnull=False
                )
                .select_related('act', 'invoice')
                .values('act__label')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('-total')[:5]
            )
            
            act_names = [a['act__label'] for a in acts]
            series = []
            
            for act_name in act_names:
                claims = (
                    Claim.objects.filter(
                        policy=self.policy_id,
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False,
                        act__label=act_name
                    )
                    .select_related('invoice')
                    .annotate(period=self.trunc_function('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
                data = [claims_map.get(period, 0.0) for period in self.periods]
                
                series.append({
                    "name": act_name,
                    "data": data
                })
            
            labels = [self._date_label(period) for period in self.periods]
            return {'series': series, 'labels': labels}
            
        except Exception as e:
            logger.error(f"Error getting top acts consumption: {e}")
            return {'series': [], 'labels': []}

    def get_top_partners_consumption(self):
        """Get top 5 partners consumption evolution and table."""
        try:
            # Get top 5 partners by total consumption
            partners = list(
                Claim.objects.filter(
                    policy=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False,
                    partner__isnull=False
                )
                .select_related('partner', 'invoice')
                .values('partner', 'partner__name')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('-total')[:5]
            )
            
            partner_tuples = [(p['partner'], p['partner__name']) for p in partners] if partners else []
            series = []
            table = []
            
            for partner_id, partner_name in partner_tuples:
                # Time series for this partner
                claims = (
                    Claim.objects.filter(
                        policy=self.policy_id,
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False,
                        partner_id=partner_id
                    )
                    .select_related('invoice')
                    .annotate(period=self.trunc_function('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
                data = [claims_map.get(period, 0.0) for period in self.periods]
                
                series.append({
                    "name": partner_name,
                    "data": data
                })
                
                # Table data for this partner
                agg = Claim.objects.filter(
                    policy=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False,
                    partner_id=partner_id
                ).aggregate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount')
                )
                
                table.append({
                    "id": partner_id,
                    "name": partner_name,
                    "claimed": self.sanitize_float(agg['total_claimed']),
                    "reimbursed": self.sanitize_float(agg['total_reimbursed'])
                })
            
            labels = [self._date_label(period) for period in self.periods]
            return {'series': series, 'labels': labels, 'table': table}
            
        except Exception as e:
            logger.error(f"Error getting top partners consumption: {e}")
            return {'series': [], 'labels': [], 'table': []}

    def get_policy_vs_client_consumption(self):
        """Get policy consumption vs other client policies."""
        try:
            if not self.policy:
                return [0, 0]
            
            # Policy consumption
            policy_consumption = Claim.objects.filter(
                policy=self.policy_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
            
            # Total client consumption (all policies)
            client_consumption = Claim.objects.filter(
                policy__client_id=self.client_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
            
            # Other policies consumption
            other_consumption = client_consumption - policy_consumption
            
            if client_consumption > 0:
                return [
                    round(100 * policy_consumption / client_consumption, 2),
                    round(100 * other_consumption / client_consumption, 2)
                ]
            
            return [0, 0]
            
        except Exception as e:
            logger.error(f"Error getting policy vs client consumption: {e}")
            return [0, 0]

    def get_complete_statistics(self):
        """Get all policy statistics in one comprehensive response."""
        try:
            logger.info(f"Generating complete statistics for policy {self.policy_id}")
            
            # Get all data series
            consumption_series = self.get_consumption_evolution()
            insured_data = self.get_insured_evolution()
            insured_by_type_series = self.get_insured_by_type_evolution()
            top_families = self.get_top_families_consumption()
            top_acts = self.get_top_acts_consumption()
            top_partners = self.get_top_partners_consumption()
            policy_vs_client = self.get_policy_vs_client_consumption()
            
            # Calculate evolution rates and actual values
            consumption_evolution_rate = self._calculate_evolution_rate(consumption_series)
            actual_consumption_value = self._get_actual_value(consumption_series)
            
            primary_evolution_rate = self._calculate_evolution_rate(insured_data['primary'])
            actual_primary_value = self._get_actual_value(insured_data['primary'])
            
            total_evolution_rate = self._calculate_evolution_rate(insured_data['total'])
            actual_total_value = self._get_actual_value(insured_data['total'])
            
            return {
                "granularity": self.granularity,
                "policy_number": self.policy.policy_number if self.policy else None,
                "consommation_percentages_client_polices": policy_vs_client,
                
                # Consumption evolution
                "consumption_series": consumption_series,
                "consumption_evolution_rate": consumption_evolution_rate,
                "actual_consumption_value": actual_consumption_value,
                
                # Primary insured evolution
                "nb_primary_series": insured_data['primary'],
                "nb_primary_evolution_rate": primary_evolution_rate,
                "actual_nb_primary_value": actual_primary_value,
                
                # Total insured evolution
                "nb_total_series": insured_data['total'],
                "nb_total_evolution_rate": total_evolution_rate,
                "actual_nb_total_value": actual_total_value,
                
                # Insured by type
                "nb_assures_par_type_series": insured_by_type_series,
                
                # Top families
                "top5_familles_conso_series": top_families['series'],
                "top5_familles_labels": top_families['labels'],
                
                # Top acts
                "top5_categories_actes_series": top_acts['series'],
                "top5_categories_labels": top_acts['labels'],
                
                # Top partners
                "top5_partners_conso_series": top_partners['series'],
                "top5_partners_labels": top_partners['labels'],
                "top_partners_table": top_partners['table']
            }
            
        except Exception as e:
            logger.error(f"Error generating complete statistics: {e}")
            return {}

##### 2
import logging
import math
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q, Sum, Count, F
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncYear
from django.utils import timezone

from ..models import (
    Policy, Claim, Invoice, InsuredEmployer, Insured, Partner, Act, ActCategory
)
from ..utils import get_granularity

logger = logging.getLogger(__name__)


class ClientPolicyStatisticsService:
    """
    Service for generating comprehensive statistics for a specific policy.
    Follows the same pattern as ClientStatisticsService with proper error handling,
    logging, and optimized queries.
    """
    
    def __init__(self, policy_id, date_start, date_end):
        """
        Initialize the service with policy ID and date range.
        
        Args:
            policy_id (int): ID of the policy to analyze
            date_start (datetime): Start date for the analysis period
            date_end (datetime): End date for the analysis period
        """
        self.policy_id = policy_id
        self.date_start = date_start
        self.date_end = date_end
        self.granularity = get_granularity(date_start, date_end)
        self.trunc_function = self._get_trunc_function()
        self.periods = self._generate_periods()
        
        # Get policy information
        try:
            self.policy = Policy.objects.select_related('client').get(pk=policy_id)
            self.client_id = self.policy.client_id
            logger.info(f"Initialized PolicyStatisticsService for policy {policy_id}")
        except Policy.DoesNotExist:
            logger.error(f"Policy {policy_id} not found")
            self.policy = None
            self.client_id = None
    
    def _get_trunc_function(self):
        """Get the appropriate truncation function based on granularity."""
        trunc_map = {
            'day': TruncDay,
            'month': TruncMonth,
            'quarter': TruncQuarter,
            'year': TruncYear
        }
        return trunc_map.get(self.granularity, TruncMonth)
    
    def _generate_periods(self):
        """Generate all periods between start and end dates based on granularity."""
        periods = []
        current = self.date_start
        
        while current <= self.date_end:
            periods.append(current)
            
            if self.granularity == 'day':
                current += timedelta(days=1)
            elif self.granularity == 'month':
                current += relativedelta(months=1)
            elif self.granularity == 'quarter':
                current += relativedelta(months=3)
            else:  # year
                current += relativedelta(years=1)
        
        return periods
    
    @staticmethod
    def sanitize_float(value):
        """Sanitize float values to prevent JSON serialization errors."""
        if value is None or math.isnan(value) or math.isinf(value):
            return 0.0
        return float(value)
    
    def _calculate_evolution_rate(self, series):
        """Calculate evolution rate between first and last values in series."""
        try:
            if not series or len(series) == 0:
                return 0.0
            
            if len(series) == 1:
                return 0.0
            
            first_val = self.sanitize_float(series[0][1] if isinstance(series[0], (list, tuple)) else series[0].get('y', 0))
            last_val = self.sanitize_float(series[-1][1] if isinstance(series[-1], (list, tuple)) else series[-1].get('y', 0))
            
            if first_val == 0:
                return "Nouveau" if last_val > 0 else 0.0
            
            return round(100 * (last_val - first_val) / abs(first_val), 2)
        except Exception as e:
            logger.error(f"Error calculating evolution rate: {e}")
            return 0.0
    
    def _get_actual_value(self, series):
        """Get the maximum value from the series (actual value over period)."""
        try:
            if not series:
                return 0.0
            
            values = []
            for item in series:
                if isinstance(item, (list, tuple)):
                    values.append(self.sanitize_float(item[1]))
                elif isinstance(item, dict):
                    values.append(self.sanitize_float(item.get('y', 0)))
            
            return max(values) if values else 0.0
        except Exception as e:
            logger.error(f"Error getting actual value: {e}")
            return 0.0
    
    def _date_label(self, dt):
        """Format date according to granularity."""
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
    
    def get_consumption_evolution(self):
        """Get consumption evolution over time."""
        try:
            claims = (
                Claim.objects.filter(
                    policy_id=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                )
                .select_related('invoice')
                .annotate(period=self.trunc_function('settlement_date'))
                .values('period')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            
            # Fill all periods with data
            claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
            series = [[int(period.timestamp()) * 1000, claims_map.get(period, 0.0)] for period in self.periods]
            
            return series
        except Exception as e:
            logger.error(f"Error getting consumption evolution: {e}")
            return []
    
    def get_insured_evolution(self):
        """Get insured employees evolution over time."""
        try:
            primary_series = []
            total_series = []
            
            for period in self.periods:
                # Count primary insured at this period
                primary_count = InsuredEmployer.objects.filter(
                    policy_id=self.policy_id,
                    role='primary',
                    start_date__lte=period
                ).filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                
                # Count total insured at this period
                total_count = InsuredEmployer.objects.filter(
                    policy_id=self.policy_id,
                    start_date__lte=period
                ).filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                
                ts = int(period.timestamp()) * 1000
                primary_series.append([ts, primary_count])
                total_series.append([ts, total_count])
            
            return {
                'primary': primary_series,
                'total': total_series
            }
        except Exception as e:
            logger.error(f"Error getting insured evolution: {e}")
            return {'primary': [], 'total': []}
    
    def get_insured_by_type_evolution(self):
        """Get insured employees evolution by type (role)."""
        try:
            role_map = {
                'primary': 'Assurés Principaux',
                'spouse': 'Assurés conjoints', 
                'child': 'Assurés enfants',
                'other': 'Autres assurés'
            }
            roles = ['primary', 'spouse', 'child', 'other']
            series = []
            
            for role in roles:
                data = []
                for period in self.periods:
                    if role == 'other':
                        count = InsuredEmployer.objects.filter(
                            policy_id=self.policy_id,
                            start_date__lte=period
                        ).exclude(role__in=['primary', 'spouse', 'child'])\
                         .filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                    else:
                        count = InsuredEmployer.objects.filter(
                            policy_id=self.policy_id,
                            role=role,
                            start_date__lte=period
                        ).filter(Q(end_date__gt=period) | Q(end_date__isnull=True)).count()
                    
                    data.append({"x": self._date_label(period), "y": count})
                
                series.append({
                    "name": role_map[role],
                    "data": data
                })
            
            return series
        except Exception as e:
            logger.error(f"Error getting insured by type evolution: {e}")
            return []
    
    def get_top_families_consumption(self):
        """Get top 5 families consumption evolution."""
        try:
            principals = InsuredEmployer.objects.filter(
                policy_id=self.policy_id, 
                role='primary'
            ).select_related('insured')
            
            family_consumptions = []
            for principal in principals:
                # Get family member IDs (principal + beneficiaries)
                family_ids = [principal.insured_id] + list(
                    InsuredEmployer.objects.filter(
                        policy_id=self.policy_id,
                        primary_insured_ref=principal.insured_id
                    ).values_list('insured_id', flat=True)
                )
                
                # Calculate total consumption for this family
                total = Claim.objects.filter(
                    policy_id=self.policy_id,
                    insured_id__in=family_ids,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False
                ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
                
                family_consumptions.append({
                    'principal': principal.insured.name,
                    'family_ids': family_ids,
                    'total': self.sanitize_float(total)
                })
            
            # Get top 5 families
            top_families = sorted(family_consumptions, key=lambda x: x['total'], reverse=True)[:5]
            
            # Generate time series for each family
            series = []
            for fam in top_families:
                claims = (
                    Claim.objects.filter(
                        policy_id=self.policy_id,
                        insured_id__in=fam['family_ids'],
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False
                    )
                    .select_related('invoice')
                    .annotate(period=self.trunc_function('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
                data = [claims_map.get(period, 0.0) for period in self.periods]
                
                series.append({
                    "name": fam['principal'],
                    "data": data
                })
            
            labels = [self._date_label(period) for period in self.periods]
            return {'series': series, 'labels': labels}
            
        except Exception as e:
            logger.error(f"Error getting top families consumption: {e}")
            return {'series': [], 'labels': []}

    def get_top_acts_consumption(self):
        """Get top 5 acts consumption evolution."""
        try:
            # Get top 5 acts by total consumption
            acts = (
                Claim.objects.filter(
                    policy_id=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False,
                    act__isnull=False
                )
                .select_related('act', 'invoice')
                .values('act__label')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('-total')[:5]
            )
            
            act_names = [a['act__label'] for a in acts]
            series = []
            
            for act_name in act_names:
                claims = (
                    Claim.objects.filter(
                        policy_id=self.policy_id,
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False,
                        act__label=act_name
                    )
                    .select_related('invoice')
                    .annotate(period=self.trunc_function('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
                data = [claims_map.get(period, 0.0) for period in self.periods]
                
                series.append({
                    "name": act_name,
                    "data": data
                })
            
            labels = [self._date_label(period) for period in self.periods]
            return {'series': series, 'labels': labels}
            
        except Exception as e:
            logger.error(f"Error getting top acts consumption: {e}")
            return {'series': [], 'labels': []}

    def get_top_partners_consumption(self):
        """Get top 5 partners consumption evolution and table."""
        try:
            # Get top 5 partners by total consumption
            partners = list(
                Claim.objects.filter(
                    policy_id=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False,
                    partner__isnull=False
                )
                .select_related('partner', 'invoice')
                .values('partner', 'partner__name')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('-total')[:5]
            )
            
            partner_tuples = [(p['partner'], p['partner__name']) for p in partners] if partners else []
            series = []
            table = []
            
            for partner_id, partner_name in partner_tuples:
                # Time series for this partner
                claims = (
                    Claim.objects.filter(
                        policy_id=self.policy_id,
                        settlement_date__range=(self.date_start, self.date_end),
                        invoice__isnull=False,
                        partner_id=partner_id
                    )
                    .select_related('invoice')
                    .annotate(period=self.trunc_function('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                claims_map = {c['period']: self.sanitize_float(c['total']) for c in claims}
                data = [claims_map.get(period, 0.0) for period in self.periods]
                
                series.append({
                    "name": partner_name,
                    "data": data
                })
                
                # Table data for this partner
                agg = Claim.objects.filter(
                    policy_id=self.policy_id,
                    settlement_date__range=(self.date_start, self.date_end),
                    invoice__isnull=False,
                    partner_id=partner_id
                ).aggregate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount')
                )
                
                table.append({
                    "id": partner_id,
                    "name": partner_name,
                    "claimed": self.sanitize_float(agg['total_claimed']),
                    "reimbursed": self.sanitize_float(agg['total_reimbursed'])
                })
            
            labels = [self._date_label(period) for period in self.periods]
            return {'series': series, 'labels': labels, 'table': table}
            
        except Exception as e:
            logger.error(f"Error getting top partners consumption: {e}")
            return {'series': [], 'labels': [], 'table': []}

    def get_policy_vs_client_consumption(self):
        """Get policy consumption vs other client policies."""
        try:
            if not self.policy:
                return [0, 0]
            
            # Policy consumption
            policy_consumption = Claim.objects.filter(
                policy_id=self.policy_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
            
            # Total client consumption (all policies)
            client_consumption = Claim.objects.filter(
                policy__client_id=self.client_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            ).aggregate(total=Sum('invoice__reimbursed_amount'))['total'] or 0
            
            # Other policies consumption
            other_consumption = client_consumption - policy_consumption
            
            if client_consumption > 0:
                return [
                    round(100 * policy_consumption / client_consumption, 2),
                    round(100 * other_consumption / client_consumption, 2)
                ]
            
            return [0, 0]
            
        except Exception as e:
            logger.error(f"Error getting policy vs client consumption: {e}")
            return [0, 0]

    def get_complete_statistics(self):
        """Get all policy statistics in one comprehensive response."""
        try:
            logger.info(f"Generating complete statistics for policy {self.policy_id}")
            
            # Get all data series
            consumption_series = self.get_consumption_evolution()
            insured_data = self.get_insured_evolution()
            insured_by_type_series = self.get_insured_by_type_evolution()
            top_families = self.get_top_families_consumption()
            top_acts = self.get_top_acts_consumption()
            top_partners = self.get_top_partners_consumption()
            policy_vs_client = self.get_policy_vs_client_consumption()
            
            # Calculate evolution rates and actual values
            consumption_evolution_rate = self._calculate_evolution_rate(consumption_series)
            actual_consumption_value = self._get_actual_value(consumption_series)
            
            primary_evolution_rate = self._calculate_evolution_rate(insured_data['primary'])
            actual_primary_value = self._get_actual_value(insured_data['primary'])
            
            total_evolution_rate = self._calculate_evolution_rate(insured_data['total'])
            actual_total_value = self._get_actual_value(insured_data['total'])
            
            return {
                "granularity": self.granularity,
                "policy_number": self.policy.policy_number if self.policy else None,
                "consommation_percentages_client_polices": policy_vs_client,
                
                # Consumption evolution
                "consumption_series": consumption_series,
                "consumption_evolution_rate": consumption_evolution_rate,
                "actual_consumption_value": actual_consumption_value,
                
                # Primary insured evolution
                "nb_primary_series": insured_data['primary'],
                "nb_primary_evolution_rate": primary_evolution_rate,
                "actual_nb_primary_value": actual_primary_value,
                
                # Total insured evolution
                "nb_total_series": insured_data['total'],
                "nb_total_evolution_rate": total_evolution_rate,
                "actual_nb_total_value": actual_total_value,
                
                # Insured by type
                "nb_assures_par_type_series": insured_by_type_series,
                
                # Top families
                "top5_familles_conso_series": top_families['series'],
                "top5_familles_labels": top_families['labels'],
                
                # Top acts
                "top5_categories_actes_series": top_acts['series'],
                "top5_categories_labels": top_acts['labels'],
                
                # Top partners
                "top5_partners_conso_series": top_partners['series'],
                "top5_partners_labels": top_partners['labels'],
                "top_partners_table": top_partners['table']
            }
            
        except Exception as e:
            logger.error(f"Error generating complete statistics: {e}")
            return {}
