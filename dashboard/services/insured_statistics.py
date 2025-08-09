from django.db.models import Sum, Count, Q, F
from django.core.exceptions import ValidationError
from core.models import Insured, InsuredEmployer, Claim, Policy, Client, Partner
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, serie_to_pairs, format_series_for_multi_line_chart,
    format_top_clients_series, format_top_insureds_series, sanitize_float
)
import logging

logger = logging.getLogger(__name__)

def fill_full_series_forward_fill(periods, serie):
    from .base import to_date
    value_map = {to_date(point['period']): point['value'] for point in serie}
    filled = []
    last_value = 0
    found_first = False
    for period in periods:
        period_date = to_date(period)
        value = value_map.get(period_date, None)
        if value is not None:
            last_value = value
            found_first = True
        elif not found_first:
            last_value = 0
        filled.append({'period': period, 'value': last_value})
    return filled

class CountryInsuredStatisticsService:
    """
    Statistiques sur les assurés d'un pays sur une période donnée.
    """
    def __init__(self, country_id, date_start_str, date_end_str):
        try:
            self.country_id = int(country_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryInsuredStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            self.country = Country.objects.get(id=self.country_id)
            # Tous les assurés du pays (via client)
            self.clients = Client.objects.filter(country_id=self.country_id)
            self.client_ids = list(self.clients.values_list('id', flat=True))
            self.policies = Policy.objects.filter(client_id__in=self.client_ids)
            self.policy_ids = list(self.policies.values_list('id', flat=True))
            self.insured_employers = InsuredEmployer.objects.filter(employer_id__in=self.client_ids)
            self.insured_ids = list(self.insured_employers.values_list('insured_id', flat=True))
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
            self.claims = Claim.objects.filter(
                insured_id__in=self.insured_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_consuming_insured_evolution(self):
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            return result
        except Exception as e:
            logger.error(f"Error in get_consuming_insured_evolution: {e}")
            return []

    def get_insured_by_role_evolution(self, role):
        try:
            result = list(
                self.insured_employers.filter(role=role, insured__creation_date__range=(self.date_start, self.date_end))
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            return result
        except Exception as e:
            logger.error(f"Error in get_insured_by_role_evolution for role {role}: {e}")
            return []

    def get_consumption_by_role(self):
        try:
            roles = ['primary', 'spouse', 'child']
            consumption_by_role = {}
            for role in roles:
                claims_role = self.claims.filter(insured__insured_clients__role=role)
                value = claims_role.aggregate(val=Sum('invoice__reimbursed_amount'))['val'] or 0
                consumption_by_role[role] = value
            return consumption_by_role
        except Exception as e:
            logger.error(f"Error in get_consumption_by_role: {e}")
            return {}

    def get_consumption_by_role_timeseries(self):
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

    def get_top_insureds_consumption_series(self, limit=10):
        try:
            # Top assurés par consommation totale
            top_insureds = list(
                self.claims.values('insured_id')
                .annotate(total_consumption=Sum('invoice__reimbursed_amount'))
                .order_by('-total_consumption')[:limit]
            )
            top_insured_ids = [c['insured_id'] for c in top_insureds]
            insured_names = {i.id: i.name for i in self.insureds.filter(id__in=top_insured_ids)}
            # Générer la série temporelle pour chaque assuré
            top_insureds_series = []
            for insured_id in top_insured_ids:
                insured_claims = self.claims.filter(insured_id=insured_id)
                insured_series = list(
                    insured_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in insured_series:
                    point['value'] = float(point['value'] or 0)
                top_insureds_series.append({
                    'insured_id': insured_id,
                    'insured_name': insured_names.get(insured_id, str(insured_id)),
                    'series': insured_series
                })
            # Format pour ApexCharts
            periods = self.periods
            series_multi, categories = format_top_insureds_series(top_insureds_series, periods, self.granularity)
            return series_multi, categories
        except Exception as e:
            logger.error(f"Error in get_top_insureds_consumption_series: {e}")
            return [], []

    def _calculate_actual_values(self, consuming_series, primary_series, spouse_series, child_series):
        def safe_last(series):
            if not series:
                return 0
            return series[-1]['value'] if isinstance(series[-1], dict) else series[-1][1]
        return {
            'actual_consuming_insured_count': safe_last(consuming_series),
            'actual_primary_insured_count': safe_last(primary_series),
            'actual_spouse_insured_count': safe_last(spouse_series),
            'actual_child_insured_count': safe_last(child_series),
        }

    def _calculate_evolution_rates(self, consuming_series, primary_series, spouse_series, child_series):
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
            'consuming_insured_evolution_rate': safe_rate(consuming_series),
            'primary_insured_evolution_rate': safe_rate(primary_series),
            'spouse_insured_evolution_rate': safe_rate(spouse_series),
            'child_insured_evolution_rate': safe_rate(child_series),
        }

    def get_complete_statistics(self):
        try:
            consuming_evolution = self.get_consuming_insured_evolution()
            primary_evolution = self.get_insured_by_role_evolution('primary')
            spouse_evolution = self.get_insured_by_role_evolution('spouse')
            child_evolution = self.get_insured_by_role_evolution('child')
            periods = self.periods
            # Forward fill
            consuming_evolution_full = fill_full_series_forward_fill(periods, consuming_evolution)
            primary_evolution_full = fill_full_series_forward_fill(periods, primary_evolution)
            spouse_evolution_full = fill_full_series_forward_fill(periods, spouse_evolution)
            child_evolution_full = fill_full_series_forward_fill(periods, child_evolution)
            consumption_by_role = self.get_consumption_by_role()
            consumption_by_role_timeseries = self.get_consumption_by_role_timeseries()
            top_insureds_series, top_insureds_categories = self.get_top_insureds_consumption_series(10)
            # Multi-line chart pour la consommation par type d'assuré
            role_labels = {
                'primary': 'Assuré principal',
                'spouse': 'Conjoint(e)',
                'child': 'Enfant',
            }
            consumption_by_role_series = format_series_for_multi_line_chart(
                consumption_by_role_timeseries, periods, self.granularity, role_labels
            )
            actual_values = self._calculate_actual_values(
                consuming_evolution_full, primary_evolution_full, spouse_evolution_full, child_evolution_full
            )
            evolution_rates = self._calculate_evolution_rates(
                consuming_evolution_full, primary_evolution_full, spouse_evolution_full, child_evolution_full
            )
            return sanitize_float({
                'granularity': self.granularity,
                'consuming_insured_evolution': serie_to_pairs(consuming_evolution_full),
                'primary_insured_evolution': serie_to_pairs(primary_evolution_full),
                'spouse_insured_evolution': serie_to_pairs(spouse_evolution_full),
                'child_insured_evolution': serie_to_pairs(child_evolution_full),
                'consumption_by_role': consumption_by_role,
                'consumption_by_role_series': consumption_by_role_series,
                'top_insureds_consumption_series': top_insureds_series,
                'top_insureds_consumption_categories': top_insureds_categories,
                **actual_values,
                **evolution_rates,
                'country': {
                    'id': self.country.id,
                    'name': self.country.name
                },
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat(),
            })
        except Exception as e:
            logger.error(f"Error in get_complete_statistics: {e}")
            return {}


class CountryInsuredListService:
    """
    Service pour retourner la liste des assurés d'un pays avec leurs informations détaillées.
    """
    def __init__(self, country_id):
        try:
            self.country_id = int(country_id)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryInsuredListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            self.country = Country.objects.get(id=self.country_id)
            # Tous les clients du pays
            self.clients = Client.objects.filter(country_id=self.country_id)
            self.client_ids = list(self.clients.values_list('id', flat=True))
            # Tous les assurés du pays (via InsuredEmployer)
            self.insured_employers = InsuredEmployer.objects.filter(employer_id__in=self.client_ids)
            self.insured_ids = list(self.insured_employers.values_list('insured_id', flat=True))
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_insureds_list(self):
        """
        Retourne la liste des assurés avec leurs informations détaillées.
        """
        try:
            # Requête optimisée avec select_related pour éviter les N+1 queries
            insured_employers = self.insured_employers.select_related(
                'insured', 'employer', 'policy'
            ).order_by('insured__name', 'employer__name')
            
            insureds_list = []
            for ie in insured_employers:
                insured = ie.insured
                client = ie.employer
                policy = ie.policy
                
                # Déterminer le nom de l'assuré principal
                primary_insured_name = "N/A"
                if ie.primary_insured_ref:
                    primary_insured_name = ie.primary_insured_ref.name
                elif ie.role == 'primary':
                    primary_insured_name = insured.name
                
                # Déterminer le type d'assuré
                insured_type = ie.get_role_display()
                
                insured_data = {
                    'insured_name': insured.name,
                    'client_name': client.name,
                    'policy_number': policy.policy_number,
                    'primary_insured_name': primary_insured_name,
                    'insured_type': insured_type,
                    'insured_id': insured.id,
                    'client': client.name,
                    'policy': policy.policy_number,
                }

                insureds_list.append(insured_data)
            
            return insureds_list
        except Exception as e:
            logger.error(f"Error in get_insureds_list: {e}")
            return []

    def get_complete_insureds_list(self):
        """
        Retourne la liste complète avec métadonnées.
        """
        try:
            insureds_list = self.get_insureds_list()
            
            return {
                'insureds_list': insureds_list,
                'total_count': len(insureds_list),
                'country': {
                    'id': self.country.id,
                    'name': self.country.name
                }
            }
        except Exception as e:
            logger.error(f"Error in get_complete_insureds_list: {e}")
            return {
                'insureds_list': [],
                'total_count': 0,
                'country': {
                    'id': self.country_id,
                    'name': 'Unknown'
                }
            }
            