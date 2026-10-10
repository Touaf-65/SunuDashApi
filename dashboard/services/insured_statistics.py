from django.db.models import Sum, Count, Q, F
from django.core.exceptions import ValidationError
from core.models import Insured, InsuredEmployer, Claim, Policy, Client, Partner
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, serie_to_pairs, format_series_for_multi_line_chart,
    format_top_clients_series, format_top_insureds_series, sanitize_float
)
from core.services.premium_service import current_summary, premium_series, sp_series, client_sp, sp_summary
from . import indicators as ind
import logging

logger = logging.getLogger(__name__)

class CountryInsuredStatisticsService:
    """
    Statistiques sur les assurés d'un pays sur une période (lot D3) : assurés **ayant consommé** (au moins un
    sinistre réglé sur la période), par rôle (adhésion portée par le sinistre), nouveaux assurés (premier sinistre
    dans la période), et assurés **inscrits** (toutes les personnes connues sur les polices du pays).
    """
    ROLE_LABELS = {
        'primary': 'Assuré principal',
        'spouse': 'Conjoint(e)',
        'child': 'Enfant',
    }

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
        self.country = Country.objects.filter(id=self.country_id).first()
        if not self.country:
            raise ValidationError(f"Pays {self.country_id} introuvable")
        self.client_ids = list(Client.objects.filter(country_id=self.country_id).values_list('id', flat=True))
        self.insured_employers = InsuredEmployer.objects.filter(policy__country_id=self.country_id)
        self.scope_claims = Claim.objects.filter(policy__country_id=self.country_id, claimed_amount__isnull=False)
        self.claims = ind.in_period(self.scope_claims, self.date_start, self.date_end)
        self.periods = generate_periods(self.date_start, self.date_end, self.granularity)

    def get_consumption_by_role(self):
        """Montant remboursé sur la période par rôle (adhésion du sinistre : un sinistre compte une seule fois)."""
        totals = dict(self.claims.values('membership__role').annotate(v=Sum('reimbursed_amount'))
                      .values_list('membership__role', 'v'))
        return {role: float(totals.get(role) or 0) for role in ind.ROLES}

    def get_consumption_by_role_timeseries(self):
        rows = (self.claims.annotate(period=self.trunc('settlement_date')).values('period', 'membership__role')
                .annotate(value=Sum('reimbursed_amount')))
        out = {role: [] for role in ind.ROLES}
        for row in rows:
            if row['membership__role'] in out:
                out[row['membership__role']].append({'period': row['period'], 'value': float(row['value'] or 0)})
        return {role: ind.fill_zero(self.periods, serie) for role, serie in out.items()}

    def get_top_insureds_consumption_series(self, limit=10):
        top_insureds = list(
            self.claims.values('insured_id')
            .annotate(total_consumption=Sum('reimbursed_amount'))
            .order_by('-total_consumption')[:limit]
        )
        top_insured_ids = [c['insured_id'] for c in top_insureds]
        insured_names = dict(Insured.objects.filter(id__in=top_insured_ids).values_list('id', 'name'))
        top_insureds_series = []
        for insured_id in top_insured_ids:
            insured_series = list(
                self.claims.filter(insured_id=insured_id).annotate(period=self.trunc('settlement_date'))
                .values('period').annotate(value=Sum('reimbursed_amount')).order_by('period')
            )
            for point in insured_series:
                point['value'] = float(point['value'] or 0)
            top_insureds_series.append({
                'insured_id': insured_id,
                'insured_name': insured_names.get(insured_id, str(insured_id)),
                'series': insured_series
            })
        return format_top_insureds_series(top_insureds_series, self.periods, self.granularity)

    def _role_counts(self, start, end):
        claims = ind.in_period(self.scope_claims, start, end)
        counts = dict(claims.values('membership__role').annotate(n=Count('insured_id', distinct=True))
                      .values_list('membership__role', 'n'))
        return {role: counts.get(role, 0) for role in ind.ROLES}

    def get_complete_statistics(self):
        current, evolutions, previous = ind.kpis_with_evolution(self.scope_claims, self.client_ids,
                                                                self.date_start, self.date_end)
        roles_now = self._role_counts(self.date_start, self.date_end)
        roles_before = self._role_counts(*ind.previous_period(self.date_start, self.date_end))
        consuming = ind.distinct_series(self.claims, self.trunc, self.periods, 'insured_id')
        by_role = ind.consumers_by_role_series(self.claims, self.trunc, self.periods)
        top_insureds_series, top_insureds_categories = self.get_top_insureds_consumption_series(10)
        return sanitize_float({
            'granularity': self.granularity,
            # Assurés ayant consommé, par tranche
            'consuming_insured_evolution': serie_to_pairs(consuming),
            'primary_insured_evolution': serie_to_pairs(by_role['primary']),
            'spouse_insured_evolution': serie_to_pairs(by_role['spouse']),
            'child_insured_evolution': serie_to_pairs(by_role['child']),
            'consumption_by_role': self.get_consumption_by_role(),
            'consumption_by_role_series': format_series_for_multi_line_chart(
                self.get_consumption_by_role_timeseries(), self.periods, self.granularity, self.ROLE_LABELS),
            'top_insureds_consumption_series': top_insureds_series,
            'top_insureds_consumption_categories': top_insureds_categories,
            # Valeurs de la période et évolution / période précédente de même durée
            'actual_consuming_insured_count': current['insureds'],
            'actual_primary_insured_count': roles_now['primary'],
            'actual_spouse_insured_count': roles_now['spouse'],
            'actual_child_insured_count': roles_now['child'],
            'actual_new_insured_count': current['new_insureds'],
            'consuming_insured_evolution_rate': evolutions['insureds'],
            'primary_insured_evolution_rate': ind.evolution(roles_now['primary'], roles_before['primary']),
            'spouse_insured_evolution_rate': ind.evolution(roles_now['spouse'], roles_before['spouse']),
            'child_insured_evolution_rate': ind.evolution(roles_now['child'], roles_before['child']),
            # Assurés inscrits (toutes périodes) sur les polices du pays
            'enrolled_insured': ind.enrolled(self.insured_employers),
            'country': {
                'id': self.country.id,
                'name': self.country.name
            },
            'date_start': self.date_start.isoformat(),
            'date_end': self.date_end.isoformat(),
        })


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
            logger.exception(f"Error in get_insureds_list: {e}")
            raise

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
            logger.exception(f"Error in get_complete_insureds_list: {e}")
            raise
            

class PolicyInsuredStatisticsService:
    """
    Service pour les statistiques détaillées des assurés d'une police spécifique.
    Fournit des analyses granulaires sur les assurés, leur consommation et leur évolution.
    """
    def __init__(self, policy_id, date_start_str, date_end_str):
        try:
            self.policy_id = int(policy_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PolicyInsuredStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            # Récupérer la police et vérifier son existence
            self.policy = Policy.objects.select_related('country').prefetch_related('employers').get(id=self.policy_id)
            
            # Récupérer tous les assurés liés à cette police
            self.insured_employers = InsuredEmployer.objects.filter(policy_id=self.policy_id)
            self.insured_ids = list(self.insured_employers.values_list('insured_id', flat=True))
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
            
            # Récupérer les claims pour cette police dans la période
            self.claims = Claim.objects.select_related('insured').filter(
                policy_id=self.policy_id,
                settlement_date__range=(self.date_start, self.date_end),
                claimed_amount__isnull=False
            )
            
            # Générer les périodes pour les séries temporelles
            self.periods = generate_periods(self.date_start, self.date_end, self.granularity)
            
        except Policy.DoesNotExist:
            raise ValidationError(f"Policy with ID {self.policy_id} does not exist")
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_insured_role_distribution(self):
        """
        Obtient la répartition des assurés par rôle (principal, conjoint, enfant, autres).
        
        Returns:
            dict: Répartition par rôle avec comptages
        """
        try:
            role_distribution = {}
            roles = ['primary', 'spouse', 'child', 'other']
            
            for role in roles:
                if role == 'other':
                    count = self.insured_employers.exclude(role__in=['primary', 'spouse', 'child']).count()
                else:
                    count = self.insured_employers.filter(role=role).count()
                role_distribution[role] = count
            
            return role_distribution
        except Exception as e:
            logger.exception(f"Error in get_insured_role_distribution: {e}")
            raise

    def get_insured_evolution_timeline(self):
        """
        Obtient l'évolution du nombre d'assurés dans le temps pour cette police.
        
        Returns:
            list: Série temporelle de l'évolution des assurés
        """
        try:
            # Arrivée d'un assuré sur la police : première consommation observée sur son adhésion
            result = list(
                self.insured_employers.filter(start_date__isnull=False).annotate(period=self.trunc('start_date'))
                .values('period')
                .annotate(value=Count('id'))
                .order_by('period')
            )
            return result
        except Exception as e:
            logger.exception(f"Error in get_insured_evolution_timeline: {e}")
            raise

    def get_insured_consumption_by_role_series(self):
        """
        Obtient les séries temporelles de consommation par rôle d'assuré.
        
        Returns:
            dict: Séries temporelles de consommation par rôle
        """
        try:
            roles = ['primary', 'spouse', 'child', 'other']
            consumption_by_role = {}
            
            for role in roles:
                if role == 'other':
                    # Pour les autres rôles, exclure primary, spouse, child
                    role_insured_ids = list(
                        self.insured_employers.exclude(role__in=['primary', 'spouse', 'child'])
                        .values_list('insured_id', flat=True)
                    )
                else:
                    role_insured_ids = list(
                        self.insured_employers.filter(role=role)
                        .values_list('insured_id', flat=True)
                    )
                
                # Filtrer les claims par rôle
                claims_role = self.claims.filter(insured_id__in=role_insured_ids)
                
                # Générer la série temporelle
                result = list(
                    claims_role.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('reimbursed_amount'))
                    .order_by('period')
                )
                
                # Convertir en float et nettoyer
                for point in result:
                    point['value'] = float(point['value'] or 0)
                
                consumption_by_role[role] = result
            
            return consumption_by_role
        except Exception as e:
            logger.exception(f"Error in get_insured_consumption_by_role_series: {e}")
            raise

    def get_top_insureds_consumption_ranking(self, limit=10):
        """
        Obtient le classement des assurés les plus consommateurs de cette police.
        
        Args:
            limit (int): Nombre maximum d'assurés à retourner
            
        Returns:
            list: Classement des assurés par consommation
        """
        try:
            # Top assurés par consommation totale
            top_insureds = list(
                self.claims.values('insured_id')
                .annotate(
                    total_consumption=Sum('reimbursed_amount'),
                    total_claimed=Sum('claimed_amount'),
                    claims_count=Count('id')
                )
                .order_by('-total_consumption')[:limit]
            )
            
            # Enrichir avec les informations des assurés
            for insured_data in top_insureds:
                insured_id = insured_data['insured_id']
                insured = self.insureds.get(id=insured_id)
                insured_employer = self.insured_employers.get(insured_id=insured_id)
                
                if insured and insured_employer:
                    insured_data['insured_name'] = insured.name
                    insured_data['role'] = insured_employer.get_role_display()
                    insured_data['role_code'] = insured_employer.role
                    insured_data['total_consumption'] = float(insured_data['total_consumption'] or 0)
                    insured_data['total_claimed'] = float(insured_data['total_claimed'] or 0)
                else:
                    insured_data['insured_name'] = f"Assuré {insured_id}"
                    insured_data['role'] = "Inconnu"
                    insured_data['role_code'] = "unknown"
            
            return top_insureds
        except Exception as e:
            logger.exception(f"Error in get_top_insureds_consumption_ranking: {e}")
            raise

    def get_insured_consumption_patterns(self):
        """
        Obtient les patterns de consommation par assuré avec des métriques détaillées.
        
        Returns:
            dict: Patterns de consommation par assuré
        """
        try:
            patterns = {}
            
            for insured_employer in self.insured_employers:
                insured_id = insured_employer.insured_id
                insured = insured_employer.insured
                role = insured_employer.role
                
                # Claims pour cet assuré
                insured_claims = self.claims.filter(insured_id=insured_id)
                
                # Calculer les métriques
                total_consumption = insured_claims.aggregate(
                    total=Sum('reimbursed_amount')
                )['total'] or 0
                
                total_claimed = insured_claims.aggregate(
                    total=Sum('claimed_amount')
                )['total'] or 0
                
                claims_count = insured_claims.count()
                
                # Calculer le ratio de remboursement
                reimbursement_ratio = 0
                if total_claimed > 0:
                    reimbursement_ratio = (total_consumption / total_claimed) * 100
                
                patterns[insured_id] = {
                    'insured_name': insured.name,
                    'role': insured_employer.get_role_display(),
                    'role_code': role,
                    'total_consumption': float(total_consumption),
                    'total_claimed': float(total_claimed),
                    'claims_count': claims_count,
                    'reimbursement_ratio': round(reimbursement_ratio, 2),
                    'average_consumption_per_claim': float(total_consumption / claims_count) if claims_count > 0 else 0
                }
            
            return patterns
        except Exception as e:
            logger.exception(f"Error in get_insured_consumption_patterns: {e}")
            raise

    def get_complete_statistics(self):
        """
        Obtient toutes les statistiques complètes sur les assurés de cette police.
        
        Returns:
            dict: Statistiques complètes formatées
        """
        try:
            # Récupérer toutes les données
            role_distribution = self.get_insured_role_distribution()
            insured_evolution = self.get_insured_evolution_timeline()
            consumption_by_role_series = self.get_insured_consumption_by_role_series()
            top_insureds_ranking = self.get_top_insureds_consumption_ranking(10)
            consumption_patterns = self.get_insured_consumption_patterns()
            
            # Calculer les valeurs actuelles
            total_insured = sum(role_distribution.values())
            total_consumption = sum(
                pattern['total_consumption'] for pattern in consumption_patterns.values()
            )
            total_claimed = sum(
                pattern['total_claimed'] for pattern in consumption_patterns.values()
            )
            
            # Calculer le ratio S/P global
            sp_ratio = 0
            if total_consumption > 0:
                # Prime entière en vigueur des employeurs de la police (historique Premium) ; absente -> 0
                employer_ids = list(self.policy.employers.values_list('id', flat=True))
                prime = sp_summary(employer_ids, self.date_start, self.date_end, Claim.objects.none())['premium']
                sp_ratio = round((total_consumption / prime) * 100, 2) if prime else 0
            
            # Formater les séries temporelles pour les graphiques
            role_labels = {
                'primary': 'Assuré principal',
                'spouse': 'Conjoint(e)',
                'child': 'Enfant',
                'other': 'Autres assurés'
            }
            
            consumption_by_role_formatted = format_series_for_multi_line_chart(
                consumption_by_role_series, self.periods, self.granularity, role_labels
            )
            
            return sanitize_float({
                'policy': {
                    'id': self.policy.id,
                    'policy_number': self.policy.policy_number,
                    'client_name': self.policy.client.name,
                    'country_name': self.policy.country.name
                },
                'granularity': self.granularity,
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat(),
                
                # Répartition des assurés
                'insured_role_distribution': role_distribution,
                'total_insured_count': total_insured,
                
                # Évolution temporelle
                'insured_evolution_timeline': insured_evolution,
                
                # Consommation par rôle
                'consumption_by_role_series': consumption_by_role_formatted,
                'total_consumption': total_consumption,
                'total_claimed': total_claimed,
                'sp_ratio': sp_ratio,
                
                # Classements et patterns
                'top_insureds_consumption_ranking': top_insureds_ranking,
                'insured_consumption_patterns': consumption_patterns,
                
                # Métadonnées
                'periods': [str(p) for p in self.periods]
            })
            
        except Exception as e:
            logger.exception(f"Error in get_complete_statistics: {e}")
            raise

    def get_complete_statistics(self):
        """
        Obtient toutes les statistiques complètes sur les assurés de cette police.
        
        Returns:
            dict: Statistiques complètes formatées
        """
        try:
            # Récupérer toutes les données
            role_distribution = self.get_insured_role_distribution()
            insured_evolution = self.get_insured_evolution_timeline()
            consumption_by_role_series = self.get_insured_consumption_by_role_series()
            top_insureds_ranking = self.get_top_insureds_consumption_ranking(10)
            consumption_patterns = self.get_insured_consumption_patterns()
            
            # Calculer les valeurs actuelles
            total_insured = sum(role_distribution.values())
            total_consumption = sum(
                pattern['total_consumption'] for pattern in consumption_patterns.values()
            )
            total_claimed = sum(
                pattern['total_claimed'] for pattern in consumption_patterns.values()
            )
            
            # Calculer le ratio S/P global
            sp_ratio = 0
            if total_consumption > 0:
                # Prime entière en vigueur des employeurs de la police (historique Premium) ; absente -> 0
                employer_ids = list(self.policy.employers.values_list('id', flat=True))
                prime = sp_summary(employer_ids, self.date_start, self.date_end, Claim.objects.none())['premium']
                sp_ratio = round((total_consumption / prime) * 100, 2) if prime else 0
            
            # Formater les séries temporelles pour les graphiques
            role_labels = {
                'primary': 'Assuré principal',
                'spouse': 'Conjoint(e)',
                'child': 'Enfant',
                'other': 'Autres assurés'
            }
            
            consumption_by_role_formatted = format_series_for_multi_line_chart(
                consumption_by_role_series, self.periods, self.granularity, role_labels
            )
            
            return sanitize_float({
                'policy': {
                    'id': self.policy.id,
                    'policy_number': self.policy.policy_number,
                    'client_name': self.policy.client.name,
                    'country_name': self.policy.country.name
                },
                'granularity': self.granularity,
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat(),
                
                # Répartition des assurés
                'insured_role_distribution': role_distribution,
                'total_insured_count': total_insured,
                
                # Évolution temporelle
                'insured_evolution_timeline': insured_evolution,
                
                # Consommation par rôle
                'consumption_by_role_series': consumption_by_role_formatted,
                'total_consumption': total_consumption,
                'total_claimed': total_claimed,
                'sp_ratio': sp_ratio,
                
                # Classements et patterns
                'top_insureds_consumption_ranking': top_insureds_ranking,
                'insured_consumption_patterns': consumption_patterns,
                
                # Métadonnées
                'periods': [str(p) for p in self.periods]
            })
            
        except Exception as e:
            logger.exception(f"Error in get_complete_statistics: {e}")
            raise


class PolicyInsuredListService:
    """
    Service pour retourner la liste détaillée des assurés d'une police avec leurs statuts,
    rôles et consommations.
    """
    def __init__(self, policy_id, date_start_str, date_end_str):
        try:
            self.policy_id = int(policy_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for PolicyInsuredListService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        try:
            # Récupérer la police et vérifier son existence
            self.policy = Policy.objects.select_related('country').prefetch_related('employers').get(id=self.policy_id)
            
            # Récupérer tous les assurés liés à cette police
            self.insured_employers = InsuredEmployer.objects.filter(policy_id=self.policy_id)
            self.insured_ids = list(self.insured_employers.values_list('insured_id', flat=True))
            self.insureds = Insured.objects.filter(id__in=self.insured_ids)
            
            # Récupérer les claims pour cette police dans la période
            self.claims = Claim.objects.select_related('insured').filter(
                policy_id=self.policy_id,
                settlement_date__range=(self.date_start, self.date_end),
                claimed_amount__isnull=False
            )
            
        except Policy.DoesNotExist:
            raise ValidationError(f"Policy with ID {self.policy_id} does not exist")
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_insureds_detailed_list(self):
        """
        Retourne la liste détaillée des assurés avec leurs statuts et consommations.
        
        Returns:
            list: Liste des assurés avec informations détaillées
        """
        try:
            insureds_list = []
            
            for insured_employer in self.insured_employers:
                insured_id = insured_employer.insured_id
                insured = insured_employer.insured
                
                # Claims pour cet assuré
                insured_claims = self.claims.filter(insured_id=insured_id)
                
                # Calculer les métriques de consommation
                consumption_data = insured_claims.aggregate(
                    total_consumption=Sum('reimbursed_amount'),
                    total_claimed=Sum('claimed_amount'),
                    claims_count=Count('id')
                )
                
                total_consumption = float(consumption_data['total_consumption'] or 0)
                total_claimed = float(consumption_data['total_claimed'] or 0)
                claims_count = consumption_data['claims_count']
                
                # Calculer le ratio de remboursement
                reimbursement_ratio = 0
                if total_claimed > 0:
                    reimbursement_ratio = round((total_consumption / total_claimed) * 100, 2)
                
                # Déterminer le nom de l'assuré principal de référence
                primary_insured_name = "N/A"
                if insured_employer.primary_insured_ref:
                    primary_insured_name = insured_employer.primary_insured_ref.name
                elif insured_employer.role == 'primary':
                    primary_insured_name = insured.name
                
                # Déterminer le statut de l'assuré
                insured_status = "Actif"
                if insured_employer.end_date and insured_employer.end_date < self.date_end.date():
                    insured_status = "Inactif"
                
                insured_data = {
                    'insured_id': insured.id,
                    'insured_name': insured.name,
                    'role': insured_employer.get_role_display(),
                    'role_code': insured_employer.role,
                    'primary_insured_name': primary_insured_name,
                    'insured_status': insured_status,
                    'start_date': insured_employer.start_date.isoformat() if insured_employer.start_date else None,
                    'end_date': insured_employer.end_date.isoformat() if insured_employer.end_date else None,
                    
                    # Métriques de consommation
                    'total_consumption': total_consumption,
                    'total_claimed': total_claimed,
                    'claims_count': claims_count,
                    'reimbursement_ratio': reimbursement_ratio,
                    'average_consumption_per_claim': round(total_consumption / claims_count, 2) if claims_count > 0 else 0,
                    
                    # Informations sur la police
                    'policy_number': self.policy.policy_number,
                    'client_name': self.policy.client.name,
                    'country_name': self.policy.country.name
                }
                
                insureds_list.append(insured_data)
            
            # Trier par rôle puis par consommation
            role_order = {'primary': 1, 'spouse': 2, 'child': 3, 'other': 4}
            insureds_list.sort(key=lambda x: (role_order.get(x['role_code'], 5), -x['total_consumption']))
            
            return insureds_list
            
        except Exception as e:
            logger.exception(f"Error in get_insureds_detailed_list: {e}")
            raise

    def get_complete_insureds_list(self):
        """
        Retourne la liste complète avec métadonnées et résumé.
        
        Returns:
            dict: Liste complète avec métadonnées
        """
        try:
            insureds_list = self.get_insureds_detailed_list()
            
            # Calculer les totaux et moyennes
            total_consumption = sum(item['total_consumption'] for item in insureds_list)
            total_claimed = sum(item['total_claimed'] for item in insureds_list)
            total_claims = sum(item['claims_count'] for item in insureds_list)
            
            # Répartition par rôle
            role_distribution = {}
            for item in insureds_list:
                role = item['role_code']
                if role not in role_distribution:
                    role_distribution[role] = 0
                role_distribution[role] += 1
            
            # Statistiques globales
            summary_stats = {
                'total_insured_count': len(insureds_list),
                'total_consumption': total_consumption,
                'total_claimed': total_claimed,
                'total_claims_count': total_claims,
                'average_consumption_per_insured': round(total_consumption / len(insureds_list), 2) if insureds_list else 0,
                'average_consumption_per_claim': round(total_consumption / total_claims, 2) if total_claims > 0 else 0,
                'global_reimbursement_ratio': round((total_consumption / total_claimed) * 100, 2) if total_claimed > 0 else 0,
                'role_distribution': role_distribution
            }
            
            return {
                'insureds_list': insureds_list,
                'summary_statistics': summary_stats,
                'policy': {
                    'id': self.policy.id,
                    'policy_number': self.policy.policy_number,
                    'client_name': self.policy.client.name,
                    'country_name': self.policy.country.name
                },
                'date_start': self.date_start.isoformat(),
                'date_end': self.date_end.isoformat()
            }
            
        except Exception as e:
            logger.exception(f"Error in get_complete_insureds_list: {e}")
            raise
            
