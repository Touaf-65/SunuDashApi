from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError
from core.models import Partner, Claim, Invoice, InsuredEmployer  
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    compute_evolution_rate, format_series_for_multi_line_chart,
    sanitize_float, format_top_clients_series
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


class CountryPartnerStatisticsService(PartnerStatisticsService):
    """
    Service to generate partner statistics for a specific country over a given period.
    Extends PartnerStatisticsService with country-specific filtering.
    """

    def __init__(self, country_id, date_start_str, date_end_str):
        """
        Initialize the service with country ID and date range.
        
        Args:
            country_id (int): ID of the country to filter partners
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.country_id = country_id
        try:
            # Get the country to verify it exists
            self.country = Country.objects.get(pk=country_id)
            super().__init__(date_start_str, date_end_str)
        except Country.DoesNotExist:
            logger.error(f"Country with ID {country_id} does not exist")
            raise ValidationError(f"Pays avec l'ID {country_id} introuvable")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryPartnerStatisticsService: {e}")
            raise ValidationError(f"Paramètres invalides: {e}")

    def _setup_base_filters(self):
        """
        Set up base filters with country-specific filtering.
        Overrides the parent method to add country filter.
        """
        try:
            # Call parent setup first
            super()._setup_base_filters()
            
            # Add country filter to the base claims queryset
            self.claims = self.claims.filter(partner__country_id=self.country_id)
            
            logger.info(f"Country {self.country_id} - Filtered claims count: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up country partner base filters: {e}")
            raise ValidationError(f"Erreur lors de la configuration des filtres: {e}")

    def get_complete_statistics(self):
        """
        Get complete statistics for partners in the specified country.
        Extends parent method to add country information.
        """
        try:
            stats = super().get_complete_statistics()
            
            # Add country information to the stats
            stats.update({
                'country': {
                    'id': self.country.id,
                    'name': self.country.name,
                    'code': self.country.code
                }
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"Error generating country partner statistics: {e}")
            return {}



class CountryPartnerListStatisticsService(PartnerListStatisticsService):
    """
    Service to retrieve a list of all partners for a specific country, sorted by consumption.
    Extends PartnerListStatisticsService with country-specific filtering.
    """

    def __init__(self, country_id, date_start_str, date_end_str):
        """
        Initialize the service with country ID and date range.
        
        Args:
            country_id (int): ID of the country to filter partners
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.country_id = country_id
        try:
            # Get the country to verify it exists
            self.country = Country.objects.get(pk=country_id)
            super().__init__(date_start_str, date_end_str)
        except Country.DoesNotExist:
            logger.error(f"Country with ID {country_id} does not exist")
            raise ValidationError(f"Pays avec l'ID {country_id} introuvable")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryPartnerListStatisticsService: {e}")
            raise ValidationError(f"Paramètres invalides: {e}")

    def _setup_base_filters(self):
        """
        Set up base filters with country-specific filtering.
        Overrides the parent method to add country filter.
        """
        try:
            # Call parent setup first
            super()._setup_base_filters()
            
            # Add country filter to the base querysets
            self.partners = self.partners.filter(country_id=self.country_id)
            self.claims = self.claims.filter(partner__country_id=self.country_id)
            
            logger.info(f"Country {self.country_id} - Filtered partners: {self.partners.count()}, Claims: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up country partner list base filters: {e}")
            raise ValidationError(f"Erreur lors de la configuration des filtres: {e}")

    def get_complete_partners_list(self):
        """
        Get complete partners list with summary statistics for the country.
        Extends parent method to add country information.
        """
        try:
            partners_list = self.get_partners_list()
            summary = self.get_partners_statistics_summary()
            
            # Add country information to the summary
            summary.update({
                'country': {
                    'id': self.country.id,
                    'name': self.country.name,
                    'code': self.country.code
                }
            })
            
            return {
                'partners_list': partners_list,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Error generating complete country partners list: {e}")
            return {
                'partners_list': [],
                'summary': {}
            }


class ClientPartnerStatisticsService(PartnerStatisticsService):
    """
    Service to generate partner statistics for a specific client over a given period.
    Extends PartnerStatisticsService with client-specific filtering.
    """

    def __init__(self, client_id, date_start_str, date_end_str):
        """
        Initialize the service with client ID and date range.
        
        Args:
            client_id (int): ID of the client to filter partners
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.client_id = client_id
        try:
            # Get the client to verify it exists
            from core.models import Client
            self.client = Client.objects.get(pk=client_id)
            super().__init__(date_start_str, date_end_str)
        except Client.DoesNotExist:
            logger.error(f"Client with ID {client_id} does not exist")
            raise ValidationError(f"Client avec l'ID {client_id} introuvable")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientPartnerStatisticsService: {e}")
            raise ValidationError(f"Paramètres invalides: {e}")

    def _setup_base_filters(self):
        """
        Set up base filters with client-specific filtering.
        Overrides the parent method to add client filter.
        """
        try:
            # Call parent setup first
            super()._setup_base_filters()
            
            # Get all insured IDs for this client
            insured_ids = list(InsuredEmployer.objects.filter(
                employer_id=self.client_id
            ).values_list('insured_id', flat=True))
            
            if not insured_ids:
                # No insured members for this client
                self.claims = self.claims.none()
            else:
                # Filter claims by insured members of this client
                self.claims = self.claims.filter(insured_id__in=insured_ids)
            
            logger.info(f"Client {self.client_id} - Filtered claims: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up client partner base filters: {e}")
            raise ValidationError(f"Erreur lors de la configuration des filtres: {e}")

    def get_complete_statistics(self):
        """
        Get complete statistics for partners of the specified client.
        Extends parent method to add client information.
        """
        try:
            stats = super().get_complete_statistics()
            
            # Add client information to the stats
            stats.update({
                'client': {
                    'id': self.client.id,
                    'name': self.client.name,
                    'code': getattr(self.client, 'code', None)
                }
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"Error generating client partner statistics: {e}")
            return {}



class ClientPartnerListStatisticsService(PartnerListStatisticsService):
    """
    Service to retrieve a list of all partners where a client's insured members have consumed,
    sorted by consumption.
    Extends PartnerListStatisticsService with client-specific filtering.
    """

    def __init__(self, client_id, date_start_str, date_end_str):
        """
        Initialize the service with client ID and date range.
        
        Args:
            client_id (int): ID of the client to filter partners
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.client_id = client_id
        try:
            # Get the client to verify it exists
            from core.models import Client
            self.client = Client.objects.get(pk=client_id)
            super().__init__(date_start_str, date_end_str)
        except Client.DoesNotExist:
            logger.error(f"Client with ID {client_id} does not exist")
            raise ValidationError(f"Client avec l'ID {client_id} introuvable")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientPartnerListStatisticsService: {e}")
            raise ValidationError(f"Paramètres invalides: {e}")

    def _setup_base_filters(self):
        """
        Set up base filters with client-specific filtering.
        Overrides the parent method to add client filter.
        """
        try:
            # Call parent setup first
            super()._setup_base_filters()
            
            # Get all insured IDs for this client
            insured_ids = list(InsuredEmployer.objects.filter(
                employer_id=self.client_id
            ).values_list('insured_id', flat=True))
            
            if not insured_ids:
                # No insured members for this client
                self.claims = self.claims.none()
            else:
                # Filter claims by insured members of this client
                self.claims = self.claims.filter(
                    insured_id__in=insured_ids
                )
            
            logger.info(f"Client {self.client_id} - Filtered claims: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up client partner list base filters: {e}")
            raise ValidationError(f"Erreur lors de la configuration des filtres: {e}")

    def get_complete_partners_list(self):
        """
        Get complete partners list with summary statistics for the client.
        Extends parent method to add client information.
        """
        try:
            partners_list = self.get_partners_list()
            summary = self.get_partners_statistics_summary()
            
            # Add client information to the summary
            summary.update({
                'client': {
                    'id': self.client.id,
                    'name': self.client.name,
                    'code': self.client.code if hasattr(self.client, 'code') else None
                }
            })
            
            return {
                'partners_list': partners_list,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Error generating complete client partners list: {e}")
            return {
                'partners_list': [],
                'summary': {}
            }


class PolicyPartnerStatisticsService(PartnerStatisticsService):
    """
    Service to generate partner statistics for a specific policy over a given period.
    Extends PartnerStatisticsService with policy-specific filtering.
    """

    def __init__(self, policy_id, date_start_str, date_end_str):
        """
        Initialize the service with policy ID and date range.
        
        Args:
            policy_id (int): ID of the policy to filter partners
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.policy_id = policy_id
        try:
            # Get the policy to verify it exists
            from core.models import Policy
            self.policy = Policy.objects.get(pk=policy_id)
            super().__init__(date_start_str, date_end_str)
        except Policy.DoesNotExist:
            logger.error(f"Policy with ID {policy_id} does not exist")
            raise ValidationError(f"Police avec l'ID {policy_id} introuvable")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PolicyPartnerStatisticsService: {e}")
            raise ValidationError(f"Paramètres invalides: {e}")

    def _setup_base_filters(self):
        """
        Set up base filters with policy-specific filtering.
        Overrides the parent method to add policy filter.
        """
        try:
            # Call parent setup first
            super()._setup_base_filters()
            
            # Filter claims by this policy
            self.claims = self.claims.filter(policy_id=self.policy_id)
            
            logger.info(f"Policy {self.policy_id} - Filtered claims: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up policy partner base filters: {e}")
            raise ValidationError(f"Erreur lors de la configuration des filtres: {e}")

    def get_complete_statistics(self):
        """
        Get complete statistics for partners of the specified policy.
        Extends parent method to add policy information.
        """
        try:
            stats = super().get_complete_statistics()
            
            # Add policy information to the stats
            stats.update({
                'policy': {
                    'id': self.policy.id,
                    'number': getattr(self.policy, 'policy_number', None)
                }
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"Error generating policy partner statistics: {e}")
            return {}


class PolicyPartnerListStatisticsService(PartnerListStatisticsService):
    """
    Service to retrieve a list of all partners where a policy's insured members have consumed,
    sorted by consumption.
    Extends PartnerListStatisticsService with policy-specific filtering.
    """

    def __init__(self, policy_id, date_start_str, date_end_str):
        """
        Initialize the service with policy ID and date range.
        
        Args:
            policy_id (int): ID of the policy to filter partners
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.policy_id = policy_id
        try:
            # Get the policy to verify it exists
            from core.models import Policy
            self.policy = Policy.objects.get(pk=policy_id)
            super().__init__(date_start_str, date_end_str)
        except Policy.DoesNotExist:
            logger.error(f"Policy with ID {policy_id} does not exist")
            raise ValidationError(f"Police avec l'ID {policy_id} introuvable")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PolicyPartnerListStatisticsService: {e}")
            raise ValidationError(f"Paramètres invalides: {e}")

    def _setup_base_filters(self):
        """
        Set up base filters with policy-specific filtering.
        Overrides the parent method to add policy filter.
        """
        try:
            # Call parent setup first
            super()._setup_base_filters()
            
            # Filter claims by this policy
            self.claims = self.claims.filter(policy_id=self.policy_id)
            
            logger.info(f"Policy {self.policy_id} - Filtered claims: {self.claims.count()}")
            
        except Exception as e:
            logger.error(f"Error setting up policy partner list base filters: {e}")
            raise ValidationError(f"Erreur lors de la configuration des filtres: {e}")

    def get_complete_partners_list(self):
        """
        Get complete partners list with summary statistics for the policy.
        Extends parent method to add policy information.
        """
        try:
            partners_list = self.get_partners_list()
            summary = self.get_partners_statistics_summary()
            
            # Add policy information to the summary
            summary.update({
                'policy': {
                    'id': self.policy.id,
                    'number': getattr(self.policy, 'policy_number', None)
                }
            })
            
            return {
                'partners_list': partners_list,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Error generating complete policy partners list: {e}")
            return {
                'partners_list': [],
                'summary': {}
            }



class PartnerStatisticsService:
    """
    Service pour générer les statistiques d'un partenaire unique (prestataire) sur une période donnée.
    """
    def __init__(self, partner_id, date_start_str, date_end_str):
        try:
            self.partner_id = int(partner_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for SinglePartnerStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            from core.models import Client, Insured, InsuredEmployer
            self.partner = Partner.objects.filter(id=self.partner_id).first()
            if not self.partner:
                raise ValidationError(f"Partner with ID {self.partner_id} does not exist")
            # Claims liés à ce partenaire
            self.claims = Claim.objects.select_related(
                'invoice', 'policy__client', 'insured', 'partner'
            ).filter(
                partner_id=self.partner_id,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            # Invoices liées à ce partenaire
            self.invoices = Invoice.objects.filter(
                provider_id=self.partner_id,
                creation_date__range=(self.date_start, self.date_end)
            )
            # Clients ayant eu des consommations chez ce partenaire
            self.client_ids = self.claims.values_list('policy__client_id', flat=True).distinct()
            self.clients = Client.objects.filter(id__in=self.client_ids)
            # Assurés ayant consommé chez ce partenaire
            self.insured_ids = self.claims.values_list('insured_id', flat=True).distinct()
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_clients_evolution(self):
        """
        Évolution du nombre de clients ayant consommé chez ce partenaire.
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Count('policy__client', distinct=True))
                .order_by('period')
            )
            for point in result:
                point['value'] = int(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_clients_evolution: {e}")
            return []

    def get_consuming_insured_evolution(self):
        """
        Évolution du nombre d'assurés ayant consommé chez ce partenaire.
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            for point in result:
                point['value'] = int(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_consuming_insured_evolution: {e}")
            return []

    def get_reimbursed_amount_evolution(self):
        """
        Évolution du montant remboursé par ce partenaire.
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            for point in result:
                point['value'] = float(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_reimbursed_amount_evolution: {e}")
            return []

    def get_claimed_amount_evolution(self):
        """
        Évolution du montant réclamé par ce partenaire.
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Sum('invoice__claimed_amount'))
                .order_by('period')
            )
            for point in result:
                point['value'] = float(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_claimed_amount_evolution: {e}")
            return []

    def get_consumption_by_role_timeseries(self):
        """
        Part de consommation par type d'assurés (principal, spouse, child, other).
        Retourne un dict {role: [ {period, value}, ... ] }
        """
        try:
            roles = ['primary', 'spouse', 'child']
            consumption_by_role = {}
            for role in roles:
                claims_role = self.claims.filter(insured__insured_clients__role=role)
                result = list(
                    claims_role.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in result:
                    point['value'] = float(point['value'] or 0)
                consumption_by_role[role] = result
            return consumption_by_role
        except Exception as e:
            logger.error(f"Error in get_consumption_by_role_timeseries: {e}")
            return {}

    def get_top_clients_consumption_series(self, limit=10):
        """
        Multi-line chart pour l'évolution des consommations des 10 clients dont les assurés ont le plus consommé chez ce partenaire.
        Retourne (series, categories) pour ApexCharts.
        """
        try:
            # Top clients par consommation totale
            top_clients = list(
                self.claims.values('policy__client_id')
                .annotate(total_consumption=Sum('invoice__reimbursed_amount'))
                .order_by('-total_consumption')[:limit]
            )
            top_client_ids = [c['policy__client_id'] for c in top_clients]
            client_names = {c.id: c.name for c in self.clients.filter(id__in=top_client_ids)}
            # Générer la série temporelle pour chaque client
            top_clients_series = []
            for client_id in top_client_ids:
                client_claims = self.claims.filter(policy__client_id=client_id)
                client_series = list(
                    client_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in client_series:
                    point['value'] = float(point['value'] or 0)
                top_clients_series.append({
                    'client_id': client_id,
                    'client_name': client_names.get(client_id, str(client_id)),
                    'series': client_series
                })
            # Format pour ApexCharts
            periods = generate_periods(self.date_start, self.date_end, self.granularity)
            series_multi, categories = format_top_clients_series(top_clients_series, periods, self.granularity)
            return series_multi, categories
        except Exception as e:
            logger.error(f"Error in get_top_clients_consumption_series: {e}")
            return [], []

    def get_acts_count_evolution(self):
        """
        Évolution du nombre de prestations (acts) réalisées chez ce partenaire.
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Count('act_id'))
                .order_by('period')
            )
            for point in result:
                point['value'] = int(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_acts_count_evolution: {e}")
            return []

    def _calculate_actual_values(self, clients_series, insured_series, reimbursed_series, claimed_series, acts_series):
        def safe_last(series):
            if not series:
                return 0
            return series[-1]['value'] if isinstance(series[-1], dict) else series[-1][1]
        return {
            'actual_clients_count': safe_last(clients_series),
            'actual_insured_count': safe_last(insured_series),
            'actual_reimbursed_amount': safe_last(reimbursed_series),
            'actual_claimed_amount': safe_last(claimed_series),
            'actual_acts_count': safe_last(acts_series),
        }

    def _calculate_evolution_rates(self, clients_series, insured_series, reimbursed_series, claimed_series, acts_series):
        def safe_rate(series):
            if not series or len(series) < 2:
                return 0.0
            v0 = series[0]['value'] if isinstance(series[0], dict) else series[0][1]
            v1 = series[-1]['value'] if isinstance(series[-1], dict) else series[-1][1]
            v0 = 0 if v0 is None else v0
            v1 = 0 if v1 is None else v1
            if v0 == 0:
                return float('inf') if v1 != 0 else 0.0
            return round((v1 - v0) / v0, 4) 
        return {
            'clients_evolution_rate': safe_rate(clients_series),
            'insured_evolution_rate': safe_rate(insured_series),
            'reimbursed_evolution_rate': safe_rate(reimbursed_series),
            'claimed_evolution_rate': safe_rate(claimed_series),
            'acts_evolution_rate': safe_rate(acts_series),
        }

    def get_complete_statistics(self):
        """
        Agrège toutes les statistiques pour le partenaire unique.
        """
        try:
            clients_evolution = self.get_clients_evolution()
            insured_evolution = self.get_consuming_insured_evolution()
            reimbursed_evolution = self.get_reimbursed_amount_evolution()
            claimed_evolution = self.get_claimed_amount_evolution()
            acts_count_evolution = self.get_acts_count_evolution()
            consumption_by_role = self.get_consumption_by_role_timeseries()
            top_clients_series, top_clients_categories = self.get_top_clients_consumption_series(10)
            periods = generate_periods(self.date_start, self.date_end, self.granularity)
            # Compléter les séries pour tous les points de la période
            clients_evolution_full = fill_full_series(periods, clients_evolution)
            insured_evolution_full = fill_full_series(periods, insured_evolution)
            reimbursed_evolution_full = fill_full_series(periods, reimbursed_evolution)
            claimed_evolution_full = fill_full_series(periods, claimed_evolution)
            acts_count_evolution_full = fill_full_series(periods, acts_count_evolution)
            # Format multi-line chart pour la consommation par type d'assuré
            role_labels = {
                'primary': 'Assuré principal',
                'spouse': 'Conjoint(e)',
                'child': 'Enfant',
            }
            consumption_by_role_series = format_series_for_multi_line_chart(
                consumption_by_role, periods, self.granularity, role_labels
            )
            actual_values = self._calculate_actual_values(
                clients_evolution_full, insured_evolution_full, reimbursed_evolution_full, claimed_evolution_full, acts_count_evolution_full
            )
            evolution_rates = self._calculate_evolution_rates(
                clients_evolution_full, insured_evolution_full, reimbursed_evolution_full, claimed_evolution_full, acts_count_evolution_full
            )
            return sanitize_float({
                'granularity': self.granularity,
                'clients_evolution': serie_to_pairs(clients_evolution_full),
                'insured_evolution': serie_to_pairs(insured_evolution_full),
                'reimbursed_amount_evolution': serie_to_pairs(reimbursed_evolution_full),
                'claimed_amount_evolution': serie_to_pairs(claimed_evolution_full),
                'acts_count_evolution': serie_to_pairs(acts_count_evolution_full),
                'consumption_by_role_series': consumption_by_role_series,
                'top_clients_consumption_series': top_clients_series,
                'top_clients_consumption_categories': top_clients_categories,
                **actual_values,
                **evolution_rates,
                'partner': {
                    'id': self.partner.id,
                    'name': self.partner.name
                },
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat(),
            })
        except Exception as e:
            logger.error(f"Error in get_complete_statistics: {e}")
            return {}


