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
from .insured_statistics import fill_full_series_forward_fill

logger = logging.getLogger(__name__)


class CountryFamilyStatisticsService:
    """
    Statistiques de consommation par famille d'un pays.
    Une famille = assuré principal + ses bénéficiaires (spouse/child).
    """
    def __init__(self, country_id, date_start_str, date_end_str):
        try:
            self.country_id = int(country_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryFamilyStatisticsService: {e}")
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
            # Claims pour la période
            self.claims = Claim.objects.filter(
                insured_id__in=self.insured_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_families_evolution(self):
        """
        Évolution du nombre de familles (assurés principaux).
        """
        try:
            result = list(
                self.insured_employers.filter(
                    role='primary',
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            return result
        except Exception as e:
            logger.error(f"Error in get_families_evolution: {e}")
            return []

    def get_spouse_count(self):
        """
        Nombre total d'assurés conjoints.
        """
        try:
            return self.insured_employers.filter(role='spouse').count()
        except Exception as e:
            logger.error(f"Error in get_spouse_count: {e}")
            return 0

    def get_child_count(self):
        """
        Nombre total d'assurés enfants.
        """
        try:
            return self.insured_employers.filter(role='child').count()
        except Exception as e:
            logger.error(f"Error in get_child_count: {e}")
            return 0

    def get_top_families_consumption_series(self, limit=15):
        """
        Évolution de consommation des 15 familles ayant le plus consommé.
        """
        try:
            # Identifier les familles (assurés principaux) avec leur consommation totale
            families_consumption = {}
            
            # Pour chaque assuré principal, calculer la consommation totale de sa famille
            primary_insureds = self.insured_employers.filter(role='primary')
            
            for primary_ie in primary_insureds:
                primary_insured = primary_ie.insured
                family_name = primary_insured.name
                
                # Trouver tous les membres de cette famille (principal + spouse + child)
                family_members = self.insured_employers.filter(
                    Q(role='primary', insured=primary_insured) |
                    Q(primary_insured_ref=primary_insured) |
                    Q(role='spouse', primary_insured_ref=primary_insured) |
                    Q(role='child', primary_insured_ref=primary_insured)
                )
                
                family_insured_ids = list(family_members.values_list('insured_id', flat=True))
                
                # Calculer la consommation totale de la famille
                family_claims = self.claims.filter(insured_id__in=family_insured_ids)
                total_consumption = family_claims.aggregate(
                    total=Sum('invoice__reimbursed_amount')
                )['total'] or 0
                
                families_consumption[primary_insured.id] = {
                    'family_name': family_name,
                    'primary_insured_id': primary_insured.id,
                    'total_consumption': total_consumption,
                    'family_insured_ids': family_insured_ids
                }
            
            # Top 15 familles par consommation
            top_families = sorted(
                families_consumption.items(),
                key=lambda x: x[1]['total_consumption'],
                reverse=True
            )[:limit]
            
            # Générer les séries temporelles pour chaque famille
            top_families_series = []
            for family_id, family_data in top_families:
                family_claims = self.claims.filter(
                    insured_id__in=family_data['family_insured_ids']
                )
                family_series = list(
                    family_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in family_series:
                    point['value'] = float(point['value'] or 0)
                
                top_families_series.append({
                    'family_id': family_id,
                    'family_name': family_data['family_name'],
                    'series': family_series
                })

            
            # Format pour ApexCharts
            series_multi, categories = format_top_insureds_series(top_families_series, self.periods, self.granularity)
            return series_multi, categories
        except Exception as e:
            logger.error(f"Error in get_top_families_consumption_series: {e}")
            return [], []

    def _calculate_actual_values(self, families_series):
        def safe_last(series):
            if not series:
                return 0
            return series[-1]['value'] if isinstance(series[-1], dict) else series[-1][1]
        return {
            'actual_families_count': safe_last(families_series),
            'actual_spouse_count': self.get_spouse_count(),
            'actual_child_count': self.get_child_count(),
        }

    def _calculate_evolution_rates(self, families_series):
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
            'families_evolution_rate': safe_rate(families_series),
        }

    def get_complete_statistics(self):
        """
        Agrège toutes les statistiques pour les familles.
        """
        try:
            families_evolution = self.get_families_evolution()
            periods = self.periods
            # Forward fill
            families_evolution_full = fill_full_series_forward_fill(periods, families_evolution)
            top_families_series, top_families_categories = self.get_top_families_consumption_series(15)
            
            actual_values = self._calculate_actual_values(families_evolution_full)
            evolution_rates = self._calculate_evolution_rates(families_evolution_full)
            
            return sanitize_float({
                'granularity': self.granularity,
                'families_evolution': serie_to_pairs(families_evolution_full),
                'top_families_consumption_series': top_families_series,
                'top_families_consumption_categories': top_families_categories,
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


class CountryFamilyListService:
    """
    Service pour lister les familles d'un pays avec leurs détails :
    - Nom du client
    - Numéro de police
    - Nombre de membres de la famille
    - Consommation sur la période choisie
    """
    def __init__(self, country_id, date_start_str, date_end_str):
        try:
            self.country_id = int(country_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountryFamilyListService: {e}")
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
            # Claims pour la période
            self.claims = Claim.objects.filter(
                insured_id__in=self.insured_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_families_list(self):
        """
        Retourne la liste des familles avec leurs détails.
        """
        try:
            families_data = []
            
            # Récupérer tous les assurés principaux du pays
            primary_insureds = self.insured_employers.filter(role='primary').select_related(
                'insured', 'employer', 'policy'
            )
            
            for primary_ie in primary_insureds:
                primary_insured = primary_ie.insured
                client = primary_ie.employer
                policy = primary_ie.policy
                
                # Trouver tous les membres de cette famille
                family_members = self.insured_employers.filter(
                    Q(role='primary', insured=primary_insured) |
                    Q(primary_insured_ref=primary_insured) |
                    Q(role='spouse', primary_insured_ref=primary_insured) |
                    Q(role='child', primary_insured_ref=primary_insured)
                ).select_related('insured')
                
                family_insured_ids = list(family_members.values_list('insured_id', flat=True))
                family_members_count = len(family_insured_ids)
                
                # Calculer la consommation de la famille sur la période
                family_claims = self.claims.filter(insured_id__in=family_insured_ids)
                family_consumption = family_claims.aggregate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount'),
                    claims_count=Count('id')
                )
                
                # Calculer le ratio S/P (Sinistres/Primes)
                sp_ratio = 0
                if client.prime and client.prime > 0:
                    sp_ratio = (family_consumption['total_reimbursed'] or 0) / float(client.prime)
                
                # Détails des membres de la famille
                family_members_details = []
                for member_ie in family_members:
                    member_insured = member_ie.insured
                    member_claims = self.claims.filter(insured=member_insured)
                    member_consumption = member_claims.aggregate(
                        total_reimbursed=Sum('invoice__reimbursed_amount')
                    )['total_reimbursed'] or 0
                    
                    family_members_details.append({
                        'id': member_insured.id,
                        'name': member_insured.name,
                        'role': member_ie.role,
                        'card_number': member_insured.card_number,
                        'consumption': float(member_consumption),
                        'is_primary': member_ie.role == 'primary'
                    })
                
                family_data = {
                    'family_id': primary_insured.id,
                    'family_name': primary_insured.name,
                    'client': {
                        'id': client.id,
                        'name': client.name,
                        'contact': client.contact
                    },
                    'policy': {
                        'id': policy.id,
                        'policy_number': policy.policy_number,
                        'creation_date': policy.creation_date.isoformat() if policy.creation_date else None
                    },
                    'family_members_count': family_members_count,
                    'family_members': family_members_details,
                    'consumption': {
                        'total_claimed': float(family_consumption['total_claimed'] or 0),
                        'total_reimbursed': float(family_consumption['total_reimbursed'] or 0),
                        'claims_count': family_consumption['claims_count'] or 0,
                        'sp_ratio': round(sp_ratio, 4)
                    },
                    'period': {
                        'start': self.date_start.isoformat(),
                        'end': self.date_end.isoformat()
                    }
                }
                
                families_data.append(family_data)
            
            # Trier par consommation (du plus élevé au plus faible)
            families_data.sort(key=lambda x: x['consumption']['total_reimbursed'], reverse=True)
            
            return {
                'families': families_data,
                'total_families': len(families_data),
                'country': {
                    'id': self.country.id,
                    'name': self.country.name
                },
                'period': {
                    'start': self.date_start.isoformat(),
                    'end': self.date_end.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_families_list: {e}")
            return {
                'families': [],
                'total_families': 0,
                'country': {
                    'id': self.country_id,
                    'name': 'Unknown'
                },
                'period': {
                    'start': self.date_start.isoformat(),
                    'end': self.date_end.isoformat()
                }
            } 


class ClientFamilyStatisticsService:
    """
    Statistiques de consommation par famille d'un client spécifique.
    Une famille = assuré principal + ses bénéficiaires (spouse/child).
    """
    def __init__(self, client_id, date_start_str, date_end_str):
        try:
            self.client_id = int(client_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientFamilyStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            # Vérifier que le client existe
            self.client = Client.objects.get(id=self.client_id)
            # Tous les assurés du client (via InsuredEmployer)
            self.insured_employers = InsuredEmployer.objects.filter(employer_id=self.client_id)
            self.insured_ids = list(self.insured_employers.values_list('insured_id', flat=True))
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
            # Claims pour la période
            self.claims = Claim.objects.filter(
                insured_id__in=self.insured_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_families_evolution(self):
        """
        Évolution du nombre de familles (assurés principaux) pour ce client.
        """
        try:
            result = list(
                self.insured_employers.filter(
                    role='primary',
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            return result
        except Exception as e:
            logger.error(f"Error in get_families_evolution: {e}")
            return []

    def get_spouse_count(self):
        """
        Nombre total d'assurés conjoints pour ce client.
        """
        try:
            return self.insured_employers.filter(role='spouse').count()
        except Exception as e:
            logger.error(f"Error in get_spouse_count: {e}")
            return 0

    def get_child_count(self):
        """
        Nombre total d'assurés enfants pour ce client.
        """
        try:
            return self.insured_employers.filter(role='child').count()
        except Exception as e:
            logger.error(f"Error in get_child_count: {e}")
            return 0

    def get_top_families_consumption_series(self, limit=15):
        """
        Évolution de consommation des familles ayant le plus consommé pour ce client.
        """
        try:
            # Identifier les familles (assurés principaux) avec leur consommation totale
            families_consumption = {}

            # Pour chaque assuré principal, calculer la consommation totale de sa famille
            primary_insureds = self.insured_employers.filter(role='primary')

            for primary_ie in primary_insureds:
                primary_insured = primary_ie.insured
                family_name = primary_insured.name

                # Trouver tous les membres de cette famille (principal + spouse + child)
                family_members = self.insured_employers.filter(
                    Q(role='primary', insured=primary_insured) |
                    Q(primary_insured_ref=primary_insured) |
                    Q(role='spouse', primary_insured_ref=primary_insured) |
                    Q(role='child', primary_insured_ref=primary_insured)
                )

                family_insured_ids = list(family_members.values_list('insured_id', flat=True))

                # Calculer la consommation totale de la famille
                family_claims = self.claims.filter(insured_id__in=family_insured_ids)
                total_consumption = family_claims.aggregate(
                    total=Sum('invoice__reimbursed_amount')
                )['total'] or 0

                families_consumption[primary_insured.id] = {
                    'family_name': family_name,
                    'primary_insured_id': primary_insured.id,
                    'total_consumption': total_consumption,
                    'family_insured_ids': family_insured_ids
                }

            # Top familles par consommation
            top_families = sorted(
                families_consumption.items(),
                key=lambda x: x[1]['total_consumption'],
                reverse=True
            )[:limit]

            # Générer les séries temporelles pour chaque famille
            top_families_series = []
            for family_id, family_data in top_families:
                family_claims = self.claims.filter(
                    insured_id__in=family_data['family_insured_ids']
                )
                family_series = list(
                    family_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in family_series:
                    point['value'] = float(point['value'] or 0)

                top_families_series.append({
                    'family_id': family_id,
                    'family_name': family_data['family_name'],
                    'series': family_series
                })

            # Format pour ApexCharts
            series_multi, categories = format_top_insureds_series(top_families_series, self.periods, self.granularity)
            return series_multi, categories
        except Exception as e:
            logger.error(f"Error in get_top_families_consumption_series: {e}")
            return [], []

    def _calculate_actual_values(self, families_series):
        def safe_last(series):
            if not series:
                return 0
            return series[-1]['value'] if isinstance(series[-1], dict) else series[-1][1]
        return {
            'actual_families_count': safe_last(families_series),
            'actual_spouse_count': self.get_spouse_count(),
            'actual_child_count': self.get_child_count(),
        }

    def _calculate_evolution_rates(self, families_series):
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
            'families_evolution_rate': safe_rate(families_series),
        }

    def get_complete_statistics(self):
        """
        Agrège toutes les statistiques pour les familles de ce client.
        """
        try:
            families_evolution = self.get_families_evolution()
            periods = self.periods
            # Forward fill
            families_evolution_full = fill_full_series_forward_fill(periods, families_evolution)
            top_families_series, top_families_categories = self.get_top_families_consumption_series(15)

            actual_values = self._calculate_actual_values(families_evolution_full)
            evolution_rates = self._calculate_evolution_rates(families_evolution_full)

            return sanitize_float({
                'granularity': self.granularity,
                'families_evolution': serie_to_pairs(families_evolution_full),
                'top_families_consumption_series': top_families_series,
                'top_families_consumption_categories': top_families_categories,
                **actual_values,
                **evolution_rates,
                'client': {
                    'id': self.client.id,
                    'name': self.client.name,
                    'contact': self.client.contact
                },
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat(),
            })
        except Exception as e:
            logger.error(f"Error in get_complete_statistics: {e}")
            return {}


class ClientFamilyListService:
    """
    Service pour lister les familles d'un client spécifique avec leurs détails :
    - Nom de la famille
    - Numéro de police
    - Nombre de membres de la famille
    - Consommation sur la période choisie
    """
    def __init__(self, client_id, date_start_str, date_end_str):
        try:
            self.client_id = int(client_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientFamilyListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            # Vérifier que le client existe
            self.client = Client.objects.get(id=self.client_id)
            # Tous les assurés du client (via InsuredEmployer)
            self.insured_employers = InsuredEmployer.objects.filter(employer_id=self.client_id)
            self.insured_ids = list(self.insured_employers.values_list('insured_id', flat=True))
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
            # Claims pour la période
            self.claims = Claim.objects.filter(
                insured_id__in=self.insured_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_families_list(self):
        """
        Retourne la liste des familles avec leurs détails pour ce client.
        """
        try:
            families_data = []

            # Récupérer tous les assurés principaux du client
            primary_insureds = self.insured_employers.filter(role='primary').select_related(
                'insured', 'policy'
            )

            for primary_ie in primary_insureds:
                primary_insured = primary_ie.insured
                policy = primary_ie.policy

                # Trouver tous les membres de cette famille
                family_members = self.insured_employers.filter(
                    Q(role='primary', insured=primary_insured) |
                    Q(primary_insured_ref=primary_insured) |
                    Q(role='spouse', primary_insured_ref=primary_insured) |
                    Q(role='child', primary_insured_ref=primary_insured)
                ).select_related('insured')

                family_insured_ids = list(family_members.values_list('insured_id', flat=True))
                family_members_count = len(family_insured_ids)

                # Calculer la consommation de la famille sur la période
                family_claims = self.claims.filter(insured_id__in=family_insured_ids)
                family_consumption = family_claims.aggregate(
                    total_claimed=Sum('invoice__claimed_amount'),
                    total_reimbursed=Sum('invoice__reimbursed_amount'),
                    claims_count=Count('id')
                )

                # Calculer le ratio S/P (Sinistres/Primes)
                sp_ratio = 0
                if self.client.prime and self.client.prime > 0:
                    sp_ratio = (family_consumption['total_reimbursed'] or 0) / float(self.client.prime)

                # Détails des membres de la famille
                family_members_details = []
                for member_ie in family_members:
                    member_insured = member_ie.insured
                    member_claims = self.claims.filter(insured=member_insured)
                    member_consumption = member_claims.aggregate(
                        total_reimbursed=Sum('invoice__reimbursed_amount')
                    )['total_reimbursed'] or 0

                    family_members_details.append({
                        'id': member_insured.id,
                        'name': member_insured.name,
                        'role': member_ie.role,
                        'card_number': member_insured.card_number,
                        'consumption': float(member_consumption),
                        'is_primary': member_ie.role == 'primary'
                    })

                family_data = {
                    'family_id': primary_insured.id,
                    'family_name': primary_insured.name,
                    'policy': {
                        'id': policy.id,
                        'policy_number': policy.policy_number,
                        'creation_date': policy.creation_date.isoformat() if policy.creation_date else None
                    },
                    'family_members_count': family_members_count,
                    'family_members': family_members_details,
                    'consumption': {
                        'total_claimed': float(family_consumption['total_claimed'] or 0),
                        'total_reimbursed': float(family_consumption['total_reimbursed'] or 0),
                        'claims_count': family_consumption['claims_count'] or 0,
                        'sp_ratio': round(sp_ratio, 4)
                    },
                    'period': {
                        'start': self.date_start.isoformat(),
                        'end': self.date_end.isoformat()
                    }
                }

                families_data.append(family_data)

            # Trier par consommation (du plus élevé au plus faible)
            families_data.sort(key=lambda x: x['consumption']['total_reimbursed'], reverse=True)

            return {
                'families': families_data,
                'total_families': len(families_data),
                'client': {
                    'id': self.client.id,
                    'name': self.client.name,
                    'contact': self.client.contact
                },
                'period': {
                    'start': self.date_start.isoformat(),
                    'end': self.date_end.isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Error in get_families_list: {e}")
            return {
                'families': [],
                'total_families': 0,
                'client': {
                    'id': self.client_id,
                    'name': 'Unknown'
                },
                'period': {
                    'start': self.date_start.isoformat(),
                    'end': self.date_end.isoformat()
                }
            } 
