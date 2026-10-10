from django.db.models import Sum, Count
from django.core.exceptions import ValidationError
from core.models import Client, Claim, InsuredEmployer, Policy
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    compute_evolution_rate, format_series_for_multi_line_chart,
    format_top_clients_series, format_countries_consumption_series
)
from core.services.premium_service import current_summary, premium_series, sp_series, client_sp, sp_summary
from .country_statistics import ScopeStatisticsService
import logging

logger = logging.getLogger(__name__)

class GlobalStatisticsService(ScopeStatisticsService):
    """Tableau de bord multi-pays (admin global) : mêmes indicateurs que pour un pays (lot D3), sur tous les pays,
    plus l'évolution de la consommation par pays. Les montants de pays différents sont additionnés tels quels
    (devises : voir le lot multi-devises)."""

    def _setup_scope(self):
        self.client_ids = list(Client.objects.values_list('id', flat=True))
        self.scope_claims = Claim.objects.filter(claimed_amount__isnull=False)
        self.insured_employers = InsuredEmployer.objects.all()

    def get_countries_consumption_multiline_series(self):
        """Consommation (remboursé) de chaque pays par tranche sur la période."""
        names = dict(Country.objects.values_list('id', 'name'))
        rows = (self.claims.annotate(period=self.trunc('settlement_date')).values('policy__country_id', 'period')
                .annotate(value=Sum('reimbursed_amount')).order_by('period'))
        by_country = {country_id: [] for country_id in names}
        for row in rows:
            by_country.setdefault(row['policy__country_id'], []).append(
                {'period': row['period'], 'value': float(row['value'] or 0)})
        return [{"country_id": country_id, "country_name": names.get(country_id, str(country_id)), "series": series}
                for country_id, series in by_country.items()]

    def get_complete_statistics(self):
        stats = super().get_complete_statistics()
        periods = generate_periods(self.date_start, self.date_end, self.granularity)
        series, categories = format_countries_consumption_series(
            self.get_countries_consumption_multiline_series(), periods, self.granularity
        )
        stats["countries_consumption_multiline_series"] = series
        stats["countries_consumption_categories"] = categories
        return stats


class CountriesListStatisticsService:
    """
    Service to retrieve country-level statistics, including:
    - Country name
    - Total premium (prime globale)
    - Total consumption (consommation globale)
    - S/P ratio (ratio of premium to consumption)
    - Number of insured individuals
    - Number of clients

    Methods:
        get_countries_statistics():
            Computes and returns a list of dictionaries, each containing the above statistics for every country.
            Aggregates data from related Client, InsuredEmployer and Claim models.
            Filters data within the date range provided at initialization.
    """

    def __init__(self, date_start_str, date_end_str):
        """
        Initializes the service with optional date filters.
        Args:
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            if date_start_str and date_end_str:
                self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            else:
                self.date_start, self.date_end = None, None
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountriesListStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def get_countries_statistics(self):
        from django.db.models import Sum, Count

        countries = Country.objects.all()
        results = []
        for country in countries:
            # Activité de la période : sinistres réglés sur la période (la date de création en base n'est que la date
            # de l'import, elle ne dit rien de l'activité)
            all_ids = list(Client.objects.filter(country=country).values_list('id', flat=True))
            claims_qs = Claim.objects.filter(country=country)
            if self.date_start and self.date_end:
                claims_qs = claims_qs.filter(settlement_date__range=(self.date_start, self.date_end))
                nb_clients = claims_qs.exclude(employer=None).values('employer').distinct().count()
                nb_assures = claims_qs.values('insured').distinct().count()
            else:
                nb_clients = len(all_ids)
                nb_assures = InsuredEmployer.objects.filter(policy__country=country).values('insured').distinct().count()

            # Consommation globale : montants remboursés des sinistres du pays sur la période
            consommation_globale = claims_qs.aggregate(total=Sum('reimbursed_amount'))['total'] or 0

            # Primes (historique Premium) et ratio S/P = consommation / prime entière en vigueur
            if self.date_start and self.date_end:
                sp = sp_summary(all_ids, self.date_start, self.date_end, claims_qs)
            else:
                sp = current_summary(all_ids, Claim.objects.filter(country=country))
            prime_globale = sp['premium']
            ratio_sp = sp['ratio']

            results.append({
                'country_id': country.id,
                'country_name': country.name,
                'prime_globale': float(prime_globale),
                'consommation_globale': float(consommation_globale),
                'ratio_sp': float(ratio_sp) if ratio_sp is not None else None,
                'nb_assures': nb_assures,
                'nb_clients': nb_clients,
            })
        return results
