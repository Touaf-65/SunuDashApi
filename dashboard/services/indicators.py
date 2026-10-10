"""
Définitions communes des indicateurs des tableaux de bord (lot D3, décisions du 10/10/2026).

- Période : sinistres filtrés sur la **date de règlement** (comme partout ailleurs).
- Montants réclamés / remboursés de la période : **sommes** sur la période (et non le maximum d'une tranche).
- Assurés : ceux qui **ont consommé** pendant la période (au moins un sinistre réglé). Le rôle (principal, conjoint,
  enfant) est celui de l'adhésion portée par le sinistre (`Claim.membership`). Les **inscrits** (toutes les personnes connues
  sur les polices du périmètre) sont donnés à part.
- Employeurs (clients) / polices actifs : ceux qui ont au moins un sinistre réglé pendant la période.
- Nouveaux employeurs / assurés : ceux dont le **premier sinistre** (date de règlement, toutes périodes confondues
  dans le périmètre) tombe dans la période. La date d'import en base n'est plus utilisée.
- Prime et S/P : règles de premium_service (prime entière en vigueur ; S/P = consommation couverte / primes).
- Évolution : comparaison avec la **période précédente de même durée** (« Nouveau » si rien avant).
- Séries : les flux (montants, nombres d'assurés ou d'employeurs actifs) valent 0 dans une tranche vide ; seule la
  prime en vigueur (un stock) est reportée d'une tranche à l'autre.
"""
from datetime import timedelta

from django.db.models import Case, Count, F, IntegerField, Min, Sum, When

from core.models import Premium
from core.services.premium_service import sp_summary
from .base import to_date

ROLES = ('primary', 'spouse', 'child')
NEW = 'Nouveau'


def previous_period(start, end):
    """Période de même durée qui précède [start, end] (bornes incluses)."""
    days = (end - start).days
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=days), prev_end


def in_period(claims, start, end):
    return claims.filter(settlement_date__range=(start, end))


def evolution(current, previous):
    """Évolution en % par rapport à la période précédente ; « Nouveau » si rien avant ; None si inconnu."""
    if current is None:
        return None
    if not previous:
        return NEW if current else 0.0
    return round(100 * (float(current) - float(previous)) / abs(float(previous)), 2)


def first_in_period(scope_claims, field, start, end):
    """Nombre d'objets (`field` : 'employer_id', 'insured_id'…) dont le premier sinistre réglé du périmètre tombe
    dans [start, end]."""
    return (scope_claims.exclude(**{f'{field}__isnull': True}).values(field)
            .annotate(first=Min('settlement_date')).filter(first__range=(start, end)).count())


def kpis(scope_claims, client_ids, start, end):
    """
    Indicateurs d'une période pour un périmètre.
    `scope_claims` : sinistres du périmètre (pays, employeur, police…) **sans** filtre de date ;
    `client_ids` : employeurs du périmètre (pour les primes).
    """
    claims = in_period(scope_claims, start, end)
    totals = claims.aggregate(claimed=Sum('claimed_amount'), reimbursed=Sum('reimbursed_amount'), claims=Count('id'))
    sp = sp_summary(client_ids, start, end, claims)
    active_employers = set(claims.exclude(employer_id__isnull=True).values_list('employer_id', flat=True).distinct())
    with_premium = set(Premium.objects.filter(client_id__in=active_employers, start_date__lte=to_date(end),
                                              end_date__gte=to_date(start)).values_list('client_id', flat=True))
    return {
        'claimed': float(totals['claimed'] or 0),
        'reimbursed': float(totals['reimbursed'] or 0),
        'claims': totals['claims'],
        'insureds': claims.values('insured_id').distinct().count(),
        'principals': claims.filter(membership__role='primary').values('insured_id').distinct().count(),
        'employers': len(active_employers),
        'policies': claims.values('policy_id').distinct().count(),
        'new_employers': first_in_period(scope_claims, 'employer_id', start, end),
        'new_insureds': first_in_period(scope_claims, 'insured_id', start, end),
        'premium': sp['premium'],
        'sp_ratio': sp['ratio'],
        'sp_consumption': sp['consumption'],
        'employers_without_premium': len(active_employers - with_premium),
    }


def kpis_with_evolution(scope_claims, client_ids, start, end):
    """(indicateurs de la période, évolutions par rapport à la période précédente de même durée)."""
    current = kpis(scope_claims, client_ids, start, end)
    prev_start, prev_end = previous_period(start, end)
    previous = kpis(scope_claims, client_ids, prev_start, prev_end)
    return current, {key: evolution(current[key], previous[key]) for key in current}, previous


def enrolled(insured_employers):
    """Assurés inscrits (personnes distinctes) et répartition par rôle, toutes périodes confondues."""
    by_role = dict(insured_employers.values('role').annotate(n=Count('insured_id', distinct=True)).values_list('role', 'n'))
    return {
        'total': insured_employers.values('insured_id').distinct().count(),
        'primary': by_role.get('primary', 0),
        'spouse': by_role.get('spouse', 0),
        'child': by_role.get('child', 0),
    }


# ------------------------------------------------------------------ séries par tranche
def fill_zero(periods, serie):
    """Série complète sur toutes les tranches ; 0 dans une tranche sans valeur (flux)."""
    values = {to_date(p['period']): p['value'] for p in serie}
    return [{'period': period, 'value': values.get(to_date(period)) or 0} for period in periods]


def sum_series(claims, trunc, periods, field):
    serie = claims.annotate(period=trunc('settlement_date')).values('period').annotate(value=Sum(field)).order_by('period')
    return fill_zero(periods, [{'period': p['period'], 'value': float(p['value'] or 0)} for p in serie])


def distinct_series(claims, trunc, periods, field):
    serie = (claims.exclude(**{f'{field}__isnull': True}).annotate(period=trunc('settlement_date')).values('period')
             .annotate(value=Count(field, distinct=True)).order_by('period'))
    return fill_zero(periods, list(serie))


def new_series(scope_claims, trunc, periods, field, start, end):
    """Nouveaux objets (premier sinistre réglé) par tranche."""
    firsts = (scope_claims.exclude(**{f'{field}__isnull': True}).values(field).annotate(first=Min('settlement_date'))
              .filter(first__range=(start, end)).values_list('first', flat=True))
    counts = {}
    for first in firsts:
        key = to_date(trunc_python(first, trunc))
        counts[key] = counts.get(key, 0) + 1
    return [{'period': period, 'value': counts.get(to_date(period), 0)} for period in periods]


def trunc_python(value, trunc):
    name = trunc.__name__
    if name == 'TruncMonth':
        return value.replace(day=1)
    if name == 'TruncQuarter':
        return value.replace(month=3 * ((value.month - 1) // 3) + 1, day=1)
    if name == 'TruncYear':
        return value.replace(month=1, day=1)
    return value


def consumers_by_role_series(claims, trunc, periods):
    """{rôle: série} des assurés distincts ayant consommé, par tranche, selon leur rôle sur la police du sinistre."""
    rows = (claims.annotate(period=trunc('settlement_date')).values('period', 'membership__role')
            .annotate(value=Count('insured_id', distinct=True)))
    out = {role: [] for role in ROLES}
    for row in rows:
        if row['membership__role'] in out:
            out[row['membership__role']].append({'period': row['period'], 'value': row['value']})
    return {role: fill_zero(periods, serie) for role, serie in out.items()}


# ------------------------------------------------------------------ familles
def _family_key():
    """Principal de la famille du sinistre : l'assuré lui-même s'il est principal sur la police, sinon le principal
    de son adhésion (une famille = un principal sur une police, comme la page Familles)."""
    return Case(When(membership__role='primary', then=F('insured_id')),
                default=F('membership__primary_insured_ref_id'), output_field=IntegerField())


def families_count(claims):
    """Familles (police, principal) ayant consommé."""
    return claims.annotate(fam=_family_key()).exclude(fam__isnull=True).values('policy_id', 'fam').distinct().count()


def families_series(claims, trunc, periods):
    rows = (claims.annotate(period=trunc('settlement_date'), fam=_family_key()).exclude(fam__isnull=True)
            .values('period', 'policy_id', 'fam').distinct())
    counts = {}
    for row in rows:
        key = to_date(row['period'])
        counts[key] = counts.get(key, 0) + 1
    return [{'period': period, 'value': counts.get(to_date(period), 0)} for period in periods]
