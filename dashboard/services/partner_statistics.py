from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError
from core.models import Partner, Claim, Invoice
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    compute_evolution_rate, format_series_for_multi_line_chart,
    sanitize_float
)
import logging

logger = logging.getLogger(__name__)


class PartnerStatisticsService:
    """
    Service to generate global statistics for all partners (prestataires) over a given period.
    """

    def __init__(self, date_start_str, date_end_str):
        """
        Initializes the service with the basic parameters.
        
        Args:
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PartnerStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        """
        Configures the base filters for queries with optimized querysets (all partners).
        """
        try:
            # All partners
            self.partners = Partner.objects.select_related('country').all()
            self.partner_ids = list(self.partners.values_list('id', flat=True))

            # Claims with partners in the date range
            self.claims = Claim.objects.select_related(
                'invoice', 'partner', 'partner__country', 'policy__client'
            ).filter(
                partner_id__in=self.partner_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Generate periods for time series
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
            
            logger.info(f"Partners: {len(self.partner_ids)}, Claims: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_partners_with_consumption_evolution(self):
        """
        Calculates the evolution of the number of partners with consumption.
        
        Returns:
            list: Time series of the number of partners with consumption
        """
        try:
            partners_evolution = []
            
            for period in self.periods:
                # Count distinct partners with claims in this period
                period_end = period
                if self.granularity == 'day':
                    from datetime import timedelta
                    period_end = period + timedelta(days=1)
                elif self.granularity == 'month':
                    from datetime import timedelta
                    period_end = period + timedelta(days=31)
                elif self.granularity == 'quarter':
                    from datetime import timedelta
                    period_end = period + timedelta(days=93)
                elif self.granularity == 'year':
                    from datetime import timedelta
                    period_end = period + timedelta(days=366)
                
                count = Claim.objects.filter(
                    partner_id__in=self.partner_ids,
                    settlement_date__gte=period,
                    settlement_date__lt=period_end,
                    invoice__isnull=False
                ).values('partner_id').distinct().count()
                
                timestamp = int(period.timestamp()) * 1000
                partners_evolution.append([timestamp, count])
            
            return partners_evolution
        except Exception as e:
            logger.error(f"Error in get_partners_with_consumption_evolution: {e}")
            return []

    def get_total_claimed_evolution(self):
        """
        Calculates the evolution of total claimed amounts.
        
        Returns:
            list: Time series of total claimed amounts
        """
        try:
            claims_data = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(total=Sum('invoice__claimed_amount'))
                .order_by('period')
            )
            
            # Create a map for quick lookup
            claims_map = {c['period']: sanitize_float(c['total'] or 0) for c in claims_data}
            
            # Fill all periods with data
            claimed_evolution = []
            for period in self.periods:
                timestamp = int(period.timestamp()) * 1000
                value = claims_map.get(period, 0)
                claimed_evolution.append([timestamp, value])
            
            return claimed_evolution
        except Exception as e:
            logger.error(f"Error in get_total_claimed_evolution: {e}")
            return []

    def get_total_reimbursed_evolution(self):
        """
        Calculates the evolution of total reimbursed amounts.
        
        Returns:
            list: Time series of total reimbursed amounts
        """
        try:
            claims_data = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(total=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            
            # Create a map for quick lookup
            claims_map = {c['period']: sanitize_float(c['total'] or 0) for c in claims_data}
            
            # Fill all periods with data
            reimbursed_evolution = []
            for period in self.periods:
                timestamp = int(period.timestamp()) * 1000
                value = claims_map.get(period, 0)
                reimbursed_evolution.append([timestamp, value])
            
            return reimbursed_evolution
        except Exception as e:
            logger.error(f"Error in get_total_reimbursed_evolution: {e}")
            return []

    def get_top_partners_table(self, limit=5):
        """
        Gets the top partners by consumption with detailed information.
        
        Args:
            limit (int): Number of top partners to return
            
        Returns:
            list: List of top partners with their statistics
        """
        try:
            top_partners = list(
                self.claims.values(
                    'partner_id', 'partner__name', 'partner__country__name'
                )
                .annotate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount'),
                    claims_count=Count('id')
                )
                .order_by('-total_reimbursed')[:limit]
            )
            
            # Format the data
            partners_table = []
            for partner in top_partners:
                partners_table.append({
                    'partner_id': partner['partner_id'],
                    'partner_name': partner['partner__name'],
                    'country_name': partner['partner__country__name'],
                    'total_claimed': sanitize_float(partner['total_claimed'] or 0),
                    'total_reimbursed': sanitize_float(partner['total_reimbursed'] or 0),
                    'claims_count': int(partner['claims_count'] or 0)
                })
            
            return partners_table
        except Exception as e:
            logger.error(f"Error in get_top_partners_table: {e}")
            return []

    def get_top_partners_consumption_series(self, limit=10):
        """
        Gets consumption evolution series for top partners.
        
        Args:
            limit (int): Number of top partners to include
            
        Returns:
            tuple: (series_data, labels) for multi-line chart
        """
        try:
            # Get top partners by total consumption
            top_partners = list(
                self.claims.values('partner_id', 'partner__name')
                .annotate(total_reimbursed=Sum('invoice__reimbursed_amount'))
                .order_by('-total_reimbursed')[:limit]
            )
            
            if not top_partners:
                return [], []
            
            # Get time series for each top partner
            series_data = []
            labels = []
            
            for partner in top_partners:
                partner_id = partner['partner_id']
                partner_name = partner['partner__name']
                
                # Get claims data for this partner
                partner_claims = list(
                    self.claims.filter(partner_id=partner_id)
                    .annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(total=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                # Create a map for quick lookup
                claims_map = {c['period']: sanitize_float(c['total'] or 0) for c in partner_claims}
                
                # Fill all periods with data
                data = []
                for period in self.periods:
                    timestamp = int(period.timestamp()) * 1000
                    value = claims_map.get(period, 0)
                    data.append([timestamp, value])
                
                series_data.append({
                    'name': partner_name,
                    'data': data
                })
                labels.append(partner_name)
            
            return series_data, labels
        except Exception as e:
            logger.error(f"Error in get_top_partners_consumption_series: {e}")
            return [], []

    def get_total_statistics(self):
        """
        Gets total aggregated statistics for all partners.
        
        Returns:
            dict: Total statistics
        """
        try:
            totals = self.claims.aggregate(
                total_claimed=Sum('invoice__claimed_amount'),
                total_reimbursed=Sum('invoice__reimbursed_amount'),
                total_claims=Count('id')
            )
            
            # Count unique partners with consumption
            unique_partners_with_consumption = self.claims.values('partner_id').distinct().count()
            
            return {
                'total_claimed': sanitize_float(totals['total_claimed'] or 0),
                'total_reimbursed': sanitize_float(totals['total_reimbursed'] or 0),
                'total_claims': int(totals['total_claims'] or 0),
                'unique_partners_with_consumption': unique_partners_with_consumption,
                'total_partners': len(self.partner_ids)
            }
        except Exception as e:
            logger.error(f"Error in get_total_statistics: {e}")
            return {
                'total_claimed': 0,
                'total_reimbursed': 0,
                'total_claims': 0,
                'unique_partners_with_consumption': 0,
                'total_partners': 0
            }
    
    def _compute_evolution_rate_from_series(self, series):
        """
        Calculates the evolution rate between the first and last point of a time series.
        
        Args:
            series (list): Time series in format [[timestamp, value], ...]
            
        Returns:
            float or str: Evolution rate as a percentage or "New"
        """
        try:
            if not series or len(series) == 0:
                return 0.0
                
            if len(series) == 1:
                return 0.0
            
            first_value = float(series[0][1] or 0)
            last_value = float(series[-1][1] or 0)
            
            if first_value == 0:
                if last_value == 0:
                    return 0.0
                else:
                    return "New"
            
            return round(100 * (last_value - first_value) / abs(first_value), 2)
        except Exception as e:
            logger.error(f"Error computing evolution rate: {e}")
            return 0.0

    def get_complete_statistics(self):
        """
        Generates comprehensive statistics for all partners.
        
        Returns:
            dict: Complete statistics for partners
        """
        try:
            # Get all evolution series
            partners_evolution = self.get_partners_with_consumption_evolution()
            claimed_evolution = self.get_total_claimed_evolution()
            reimbursed_evolution = self.get_total_reimbursed_evolution()
            
            # Get top partners data
            top_partners_table = self.get_top_partners_table(5)
            top_partners_series, top_partners_labels = self.get_top_partners_consumption_series(10)
            
            # Get total statistics
            total_stats = self.get_total_statistics()
            
            # Calculate evolution rates manually since our format is [[timestamp, value], ...]
            partners_evolution_rate = self._compute_evolution_rate_from_series(partners_evolution)
            claimed_evolution_rate = self._compute_evolution_rate_from_series(claimed_evolution)
            reimbursed_evolution_rate = self._compute_evolution_rate_from_series(reimbursed_evolution)
            
            # Get actual values (latest values)
            actual_partners_count = partners_evolution[-1][1] if partners_evolution else 0
            actual_claimed_amount = claimed_evolution[-1][1] if claimed_evolution else 0
            actual_reimbursed_amount = reimbursed_evolution[-1][1] if reimbursed_evolution else 0
            
            return {
                # Time series
                'partners_with_consumption_evolution': partners_evolution,
                'total_claimed_evolution': claimed_evolution,
                'total_reimbursed_evolution': reimbursed_evolution,
                
                # Evolution rates
                'partners_evolution_rate': partners_evolution_rate,
                'claimed_evolution_rate': claimed_evolution_rate,
                'reimbursed_evolution_rate': reimbursed_evolution_rate,
                
                # Actual values
                'actual_partners_count': actual_partners_count,
                'actual_claimed_amount': actual_claimed_amount,
                'actual_reimbursed_amount': actual_reimbursed_amount,
                
                # Top partners
                'top_partners_table': top_partners_table,
                'top_partners_consumption_series': top_partners_series,
                'top_partners_labels': top_partners_labels,
                
                # Total statistics
                'total_statistics': total_stats,
                
                # Metadata
                'granularity': self.granularity,
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating complete partner statistics: {e}")
            return {}


class PartnerListStatisticsService:
    """
    Service to retrieve a list of all partners sorted by consumption with detailed information.
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
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PartnerListStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_filters(self):
        """
        Set up base querysets for partners and claims.
        """
        try:
            # All partners
            self.partners = Partner.objects.select_related('country').all()
            
            # Claims with partners in the date range
            self.claims = Claim.objects.select_related(
                'invoice', 'partner', 'partner__country'
            ).filter(
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False,
                partner__isnull=False
            )
            
            logger.info(f"Total partners: {self.partners.count()}, Claims in period: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_partners_list(self):
        """
        Get list of all partners with their consumption statistics, sorted by reimbursed amount.
        
        Returns:
            list: List of partners with their statistics
        """
        try:
            # Get partners with their consumption data
            partners_data = list(
                self.claims.values(
                    'partner_id',
                    'partner__name',
                    'partner__country__name'
                )
                .annotate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount'),
                    claims_count=Count('id')
                )
                .order_by('-total_reimbursed')
            )
            
            # Format the data
            partners_list = []
            for partner in partners_data:
                partners_list.append({
                    'partner_id': partner['partner_id'],
                    'partner_name': partner['partner__name'],
                    'country_name': partner['partner__country__name'],
                    'total_claimed': sanitize_float(partner['total_claimed'] or 0),
                    'total_reimbursed': sanitize_float(partner['total_reimbursed'] or 0),
                    'claims_count': int(partner['claims_count'] or 0)
                })
            
            # Get partners with no consumption in the period
            partners_with_consumption = {p['partner_id'] for p in partners_data}
            partners_without_consumption = self.partners.exclude(
                id__in=partners_with_consumption
            ).values('id', 'name', 'country__name')
            
            # Add partners with zero consumption
            for partner in partners_without_consumption:
                partners_list.append({
                    'partner_id': partner['id'],
                    'partner_name': partner['name'],
                    'country_name': partner['country__name'],
                    'total_claimed': 0.0,
                    'total_reimbursed': 0.0,
                    'claims_count': 0
                })
            
            return partners_list
            
        except Exception as e:
            logger.error(f"Error in get_partners_list: {e}")
            return []
    
    def get_partners_statistics_summary(self):
        """
        Get summary statistics for all partners.
        
        Returns:
            dict: Summary statistics
        """
        try:
            # Get total statistics
            totals = self.claims.aggregate(
                total_claimed=Sum('invoice__claimed_amount'),
                total_reimbursed=Sum('invoice__reimbursed_amount'),
                total_claims=Count('id')
            )
            
            # Count partners
            total_partners = self.partners.count()
            partners_with_consumption = self.claims.values('partner_id').distinct().count()
            partners_without_consumption = total_partners - partners_with_consumption
            
            return {
                'total_partners': total_partners,
                'partners_with_consumption': partners_with_consumption,
                'partners_without_consumption': partners_without_consumption,
                'total_claimed': sanitize_float(totals['total_claimed'] or 0),
                'total_reimbursed': sanitize_float(totals['total_reimbursed'] or 0),
                'total_claims': int(totals['total_claims'] or 0),
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in get_partners_statistics_summary: {e}")
            return {
                'total_partners': 0,
                'partners_with_consumption': 0,
                'partners_without_consumption': 0,
                'total_claimed': 0.0,
                'total_reimbursed': 0.0,
                'total_claims': 0,
                'date_start': self.date_start.isoformat() if hasattr(self, 'date_start') else None,
                'date_end': self.date_end.isoformat() if hasattr(self, 'date_end') else None
            }
    
    def get_complete_partners_list(self):
        """
        Get complete partners list with summary statistics.
        
        Returns:
            dict: Complete partners data with summary
        """
        try:
            partners_list = self.get_partners_list()
            summary = self.get_partners_statistics_summary()
            
            return {
                'partners_list': partners_list,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Error generating complete partners list: {e}")
            return {
                'partners_list': [],
                'summary': {}
            }
