from django.db.models import Sum
from django.core.exceptions import ValidationError
from core.models import Client, Claim, InsuredEmployer
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    format_series_for_multi_line_chart, format_top_clients_series,
)
from . import indicators as ind
from core.services.premium_service import premium_series, sp_series, sp_summary
import logging

logger = logging.getLogger(__name__)

ROLE_LABELS = {
    'primary': 'Assurés principaux',
    'spouse': 'Conjoints',
    'child': 'Enfants',
}


class ScopeStatisticsService:
    """
    Tableau de bord d'un périmètre (un pays, ou tous les pays) sur une période : indicateurs définis dans
    `indicators.py` (lot D3). Les sous-classes fixent le périmètre dans `_setup_scope()` :
    `self.client_ids` (employeurs), `self.scope_claims` (sinistres sans filtre de date),
    `self.insured_employers` (adhésions, pour les inscrits).
    """

    def __init__(self, date_start_str, date_end_str):
        try:
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_scope()
            self.claims = ind.in_period(self.scope_claims, self.date_start, self.date_end)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for {type(self).__name__}: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_scope(self):
        raise NotImplementedError

    def get_top_clients_consumption(self, limit=5):
        """Les `limit` employeurs qui ont le plus consommé (remboursé) sur la période, avec leur série."""
        top_clients = list(
            self.claims.values('employer_id')
            .annotate(total_consumption=Sum('reimbursed_amount'))
            .order_by('-total_consumption')[:limit]
        )
        top_client_ids = [c['employer_id'] for c in top_clients]
        client_names = {c.id: c.name for c in Client.objects.filter(id__in=top_client_ids)}
        top_clients_series = []
        for client_id in top_client_ids:
            client_series = list(
                self.claims.filter(employer_id=client_id).annotate(period=self.trunc('settlement_date'))
                .values('period').annotate(value=Sum('reimbursed_amount')).order_by('period')
            )
            for point in client_series:
                point['value'] = float(point['value'] or 0)
            top_clients_series.append({
                "client_id": client_id,
                "client_name": client_names.get(client_id, str(client_id)),
                "series": client_series
            })
        return top_clients_series

    def get_complete_statistics(self):
        periods = generate_periods(self.date_start, self.date_end, self.granularity)
        current, evolutions, previous = ind.kpis_with_evolution(self.scope_claims, self.client_ids,
                                                                self.date_start, self.date_end)
        prev_start, prev_end = ind.previous_period(self.date_start, self.date_end)

        # Séries par tranche : flux à 0 dans une tranche vide ; la prime en vigueur (stock) est reportée
        clients_series = ind.distinct_series(self.claims, self.trunc, periods, 'employer_id')
        new_clients_series = ind.new_series(self.scope_claims, self.trunc, periods, 'employer_id',
                                            self.date_start, self.date_end)
        primes_series = fill_full_series(periods, premium_series(self.client_ids, periods, self.date_end))
        reimbursed_series = ind.sum_series(self.claims, self.trunc, periods, 'reimbursed_amount')
        claimed_series = ind.sum_series(self.claims, self.trunc, periods, 'claimed_amount')
        partners_series = ind.distinct_series(self.claims, self.trunc, periods, 'partner_id')
        total_insured_series = ind.distinct_series(self.claims, self.trunc, periods, 'insured_id')
        by_role = ind.consumers_by_role_series(self.claims, self.trunc, periods)
        sp_ratio_series = sp_series(self.client_ids, periods, self.date_end, self.claims)

        top_clients_series_multi, top_clients_categories = format_top_clients_series(
            self.get_top_clients_consumption(), periods, self.granularity
        )

        return {
            "granularity": self.granularity,
            "period": {
                "date_start": self.date_start.date().isoformat(), "date_end": self.date_end.date().isoformat(),
                "previous_start": prev_start.date().isoformat(), "previous_end": prev_end.date().isoformat(),
            },
            # Séries
            "clients_series": serie_to_pairs(clients_series),
            "nouveaux_clients_series": serie_to_pairs(new_clients_series),
            "prime_globale_series": serie_to_pairs(primes_series),
            "montant_rembourse_series": serie_to_pairs(reimbursed_series),
            "montant_reclame_series": serie_to_pairs(claimed_series),
            "partners_series": serie_to_pairs(partners_series),
            "sp_ratio_series": serie_to_pairs(sp_ratio_series),
            "nb_assures_principaux_series": serie_to_pairs(by_role['primary']),
            "nb_assures_total_series": serie_to_pairs(total_insured_series),
            "nb_assures_par_type_series": format_series_for_multi_line_chart(by_role, periods, self.granularity,
                                                                             ROLE_LABELS),
            "top5_clients_conso_series": top_clients_series_multi,
            "top5_clients_conso_categories": top_clients_categories,
            # S/P de la période : consommation couverte / primes entières en vigueur
            "sp_ratio_total": sp_summary(self.client_ids, self.date_start, self.date_end, self.claims),
            # Valeurs de la période (sommes, effectifs distincts) et évolution / période précédente de même durée
            "actual_nb_clients_value": current['employers'],
            "actual_nouveaux_clients_value": current['new_employers'],
            "actual_prime_globale_value": current['premium'],
            "actual_sp_ratio_value": current['sp_ratio'],
            "actual_montant_rembourse_value": current['reimbursed'],
            "actual_montant_reclame_value": current['claimed'],
            "actual_nb_sinistres_value": current['claims'],
            "actual_nb_assures_principaux_value": current['principals'],
            "actual_nb_assures_total_value": current['insureds'],
            "actual_nouveaux_assures_value": current['new_insureds'],
            "actual_employeurs_sans_prime_value": current['employers_without_premium'],
            "nb_assures_inscrits": ind.enrolled(self.insured_employers),
            "clients_evolution_rate": evolutions['employers'],
            "prime_globale_evolution_rate": evolutions['premium'],
            "sp_ratio_evolution_rate": evolutions['sp_ratio'],
            "montant_rembourse_evolution_rate": evolutions['reimbursed'],
            "montant_reclame_evolution_rate": evolutions['claimed'],
            "nb_assures_principaux_evolution_rate": evolutions['principals'],
            "nb_assures_total_evolution_rate": evolutions['insureds'],
            "previous_values": previous,
        }


class CountryStatisticsService(ScopeStatisticsService):
    """Tableau de bord d'un pays."""

    def __init__(self, country_id, date_start_str, date_end_str):
        try:
            self.country_id = int(country_id)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid parameters: {e}")
        super().__init__(date_start_str, date_end_str)

    def _setup_scope(self):
        self.client_ids = list(Client.objects.filter(country_id=self.country_id).values_list('id', flat=True))
        self.scope_claims = Claim.objects.filter(policy__country_id=self.country_id, claimed_amount__isnull=False)
        self.insured_employers = InsuredEmployer.objects.filter(policy__country_id=self.country_id)
