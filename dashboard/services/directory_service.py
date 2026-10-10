"""
Listes et fiches des assurés, prestataires et opérateurs de saisie (lot D4, décisions du 10/10/2026).

Mêmes définitions que les tableaux de bord (`indicators.py`, lot D3) : période sur la date de règlement des
sinistres, montants = sommes de la période, évolution par rapport à la période précédente de même durée.
- Assurés : une ligne par personne (ses adhésions sont listées) ; la fiche montre ses sinistres et leurs lignes.
- Prestataires : activité tirée de leurs sinistres.
- Opérateurs : la colonne « opérateur » des fichiers d'import, portée par chaque **ligne** de sinistre ; leur
  activité se compte donc en lignes traitées (« interventions »).
"""
from django.db.models import Count, F, Max, Q, Sum, TextField
from django.db.models.functions import Cast

from core.models import Claim, ClaimLine, Insured, InsuredEmployer, Operator, Partner
from .base import (generate_periods, get_granularity, get_trunc_function, parse_date_range, serie_to_pairs,
                   to_date)
from . import indicators as ind

PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
TOP = 10


class DirectoryError(ValueError):
    """Paramètre invalide (message en français pour l'utilisateur)."""


# ------------------------------------------------------------------ outils
class Period:
    """Période demandée (date_start / date_end obligatoires) et découpage pour les graphiques."""

    def __init__(self, params):
        try:
            self.start, self.end = parse_date_range(params.get('date_start'), params.get('date_end'))
        except ValueError:
            raise DirectoryError("date_start et date_end sont requis (format AAAA-MM-JJ).")
        if self.end < self.start:
            raise DirectoryError("La date de fin précède la date de début.")
        self.granularity = get_granularity(self.start, self.end)
        self.trunc = get_trunc_function(self.granularity)
        self.periods = generate_periods(self.start, self.end, self.granularity)
        self.previous = ind.previous_period(self.start, self.end)

    def as_json(self):
        return {'date_start': self.start.date().isoformat(), 'date_end': self.end.date().isoformat(),
                'previous_start': self.previous[0].date().isoformat(),
                'previous_end': self.previous[1].date().isoformat(), 'granularity': self.granularity}


def _int(value, default, low=1, high=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    value = max(low, value)
    return min(value, high) if high else value


def _paginate(items_or_qs, params):
    page_size = _int(params.get('page_size'), PAGE_SIZE, 1, MAX_PAGE_SIZE)
    count = items_or_qs.count() if hasattr(items_or_qs, 'count') and not isinstance(items_or_qs, list) else len(items_or_qs)
    pages = max(1, -(-count // page_size))
    page = _int(params.get('page'), 1, 1, pages)
    start = (page - 1) * page_size
    return list(items_or_qs[start:start + page_size]), {'count': count, 'page': page, 'pages': pages, 'page_size': page_size}


def _money(value):
    return round(float(value or 0), 2)


def _rate(reimbursed, claimed):
    """Taux de remboursement (remboursé / réclamé), 4 décimales ; None sans montant réclamé."""
    return round(float(reimbursed) / float(claimed), 4) if claimed else None


def _date(value):
    return to_date(value).isoformat() if value else None


def _top(queryset, key, label, limit=TOP, amount='reimbursed_amount'):
    rows = (queryset.values(key, label).annotate(count=Count('id'), reimbursed=Sum(amount), claimed=Sum('claimed_amount'))
            .order_by('-reimbursed')[:limit])
    return [{'id': r[key], 'label': r[label] or '—', 'count': r['count'], 'reimbursed': _money(r['reimbursed']),
             'claimed': _money(r['claimed'])} for r in rows]


def _claim_activity(scope_claims, period):
    """Indicateurs et graphiques d'un ensemble de sinistres (assuré, prestataire)."""
    current, evolutions, previous = ind.kpis_with_evolution(scope_claims, [], period.start, period.end)
    claims = ind.in_period(scope_claims, period.start, period.end)
    lines = ClaimLine.objects.filter(claim__in=claims)
    by_category = (lines.values('category__label').annotate(reimbursed=Sum('reimbursed_amount'), count=Count('id'))
                   .order_by('-reimbursed'))
    kpis = {key: current[key] for key in ('claimed', 'reimbursed', 'claims', 'insureds', 'employers', 'policies')}
    kpis['lines'] = lines.count()
    kpis['reimbursement_rate'] = _rate(current['reimbursed'], current['claimed'])
    return {
        'kpis': kpis,
        'evolution': {key: evolutions[key] for key in ('claimed', 'reimbursed', 'claims', 'insureds', 'employers')},
        'previous': {key: previous[key] for key in ('claimed', 'reimbursed', 'claims', 'insureds', 'employers')},
        'reimbursed_series': serie_to_pairs(ind.sum_series(claims, period.trunc, period.periods, 'reimbursed_amount')),
        'claimed_series': serie_to_pairs(ind.sum_series(claims, period.trunc, period.periods, 'claimed_amount')),
        'by_category': [{'label': r['category__label'] or '—', 'reimbursed': _money(r['reimbursed']), 'count': r['count']}
                        for r in by_category],
        'top_acts': _top(lines, 'act_id', 'act__label'),
    }, claims


def _line_json(line):
    return {
        'line_number': line.line_number, 'act': line.act.label if line.act_id else None,
        'category': line.category.label, 'guarantee': line.guarantee_label or None,
        'invoice': line.invoice.invoice_number if line.invoice_id else None,
        'operator': {'id': line.operator_id, 'name': line.operator.name} if line.operator_id else None,
        'settlement_date': _date(line.settlement_date), 'status': line.status,
        'claimed': _money(line.claimed_amount), 'reimbursed': _money(line.reimbursed_amount), 'note': line.note or None,
    }


def _claims_page(claims, params, with_insured=True):
    """Sinistres (récents d'abord) avec leurs lignes d'actes."""
    qs = (claims.select_related('insured', 'partner', 'policy', 'employer', 'payment', 'membership')
          .prefetch_related('lines__act', 'lines__category', 'lines__invoice', 'lines__operator')
          .order_by('-settlement_date', '-id'))
    page, meta = _paginate(qs, params)
    results = []
    for c in page:
        row = {
            'id': c.id, 'number': c.number, 'status': c.status, 'claim_date': _date(c.claim_date),
            'settlement_date': _date(c.settlement_date),
            'partner': {'id': c.partner_id, 'name': c.partner.name},
            'policy': {'id': c.policy_id, 'number': c.policy.policy_number},
            'employer': {'id': c.employer_id, 'name': c.employer.name} if c.employer_id else None,
            'payment': {'reference': c.payment.reference, 'date': _date(c.payment.payment_date)} if c.payment_id else None,
            'claimed': _money(c.claimed_amount), 'reimbursed': _money(c.reimbursed_amount),
            'lines': [_line_json(l) for l in sorted(c.lines.all(), key=lambda l: l.line_number)],
        }
        if with_insured:
            row['insured'] = {'id': c.insured_id, 'name': c.insured.name, 'role': c.membership.role}
        results.append(row)
    return {**meta, 'results': results}


def _memberships_json(memberships):
    out = []
    for m in memberships:
        rate = m.plan.coverage_rate if m.plan_id and m.plan.coverage_rate is not None else m.policy.coverage_rate
        principal = m.insured if m.role == 'primary' else m.primary_insured_ref
        out.append({
            'id': m.id, 'role': m.role, 'role_label': dict(InsuredEmployer.ROLE_CHOICES).get(m.role, m.role),
            'policy': {'id': m.policy_id, 'number': m.policy.policy_number},
            'employer': {'id': m.employer_id, 'name': m.employer.name} if m.employer_id else None,
            'plan': m.plan.label if m.plan_id else None,
            'coverage_rate': float(rate) if rate is not None else None,
            'principal': {'id': principal.id, 'name': principal.name} if principal else None,
            'start_date': _date(m.start_date), 'end_date': _date(m.end_date),
        })
    return out


# ------------------------------------------------------------------ assurés
def insured_directory(country_id, params):
    period = Period(params)
    insureds = Insured.objects.filter(country_id=country_id)
    search = (params.get('search') or '').strip()
    if search:
        # Nom, autres écritures rencontrées dans les fichiers, ou n° de carte
        insureds = insureds.annotate(other_names_text=Cast('other_names', TextField())).filter(
            Q(name__icontains=search) | Q(card_number__icontains=search) | Q(other_names_text__icontains=search))
    links = InsuredEmployer.objects.filter(policy__country_id=country_id)
    role = params.get('role')
    if role in ind.ROLES:
        links = links.filter(role=role)
    if params.get('employer'):
        links = links.filter(employer_id=_int(params.get('employer'), 0))
    if params.get('policy'):
        links = links.filter(policy_id=_int(params.get('policy'), 0))
    if role in ind.ROLES or params.get('employer') or params.get('policy'):
        insureds = insureds.filter(id__in=links.values('insured_id'))
    in_period = Q(claims__settlement_date__range=(period.start, period.end))
    insureds = insureds.annotate(
        claims_count=Count('claims', filter=in_period),
        claimed=Sum('claims__claimed_amount', filter=in_period),
        reimbursed=Sum('claims__reimbursed_amount', filter=in_period),
        last_care=Max('claims__claim_date', filter=in_period),
    )
    if params.get('consumed') in ('1', 'true'):
        insureds = insureds.filter(claims_count__gt=0)
    order = {'name': ('name', 'id'), '-claims': ('-claims_count', 'name')}.get(params.get('sort'))
    insureds = insureds.order_by(*order) if order else insureds.order_by(F('reimbursed').desc(nulls_last=True), 'name')
    page, meta = _paginate(insureds, params)
    memberships = {}
    for m in (InsuredEmployer.objects.filter(insured_id__in=[i.id for i in page], policy__country_id=country_id)
              .select_related('policy', 'employer', 'plan', 'insured', 'primary_insured_ref').order_by('id')):
        memberships.setdefault(m.insured_id, []).append(m)
    results = [{
        'id': i.id, 'name': i.name, 'card_number': i.card_number,
        'memberships': _memberships_json(memberships.get(i.id, [])),
        'claims': i.claims_count, 'claimed': _money(i.claimed), 'reimbursed': _money(i.reimbursed),
        'last_care': _date(i.last_care),
    } for i in page]
    scope = Claim.objects.filter(policy__country_id=country_id)
    claims = ind.in_period(scope, period.start, period.end)
    consumers = dict(claims.values('membership__role').annotate(n=Count('insured_id', distinct=True))
                     .values_list('membership__role', 'n'))
    summary = {
        'enrolled': ind.enrolled(InsuredEmployer.objects.filter(policy__country_id=country_id)),
        'consumers': {'total': claims.values('insured_id').distinct().count(),
                      **{r: consumers.get(r, 0) for r in ind.ROLES}},
    }
    return {**meta, 'period': period.as_json(), 'summary': summary, 'results': results}


def insured_sheet(insured_id, params):
    period = Period(params)
    insured = Insured.objects.select_related('country').get(id=insured_id)
    scope = Claim.objects.filter(insured_id=insured_id)
    activity, claims = _claim_activity(scope, period)
    memberships = list(InsuredEmployer.objects.filter(insured_id=insured_id)
                       .select_related('policy', 'employer', 'plan', 'insured', 'primary_insured_ref').order_by('id'))
    families = []
    for m, data in zip(memberships, _memberships_json(memberships)):
        principal = data['principal']
        own = claims.filter(policy_id=m.policy_id).aggregate(s=Sum('reimbursed_amount'))['s'] or 0
        family_total = 0
        if principal:
            family_total = ind.in_period(Claim.objects.filter(policy_id=m.policy_id).filter(
                Q(membership__role='primary', insured_id=principal['id'])
                | Q(membership__primary_insured_ref_id=principal['id'])), period.start, period.end) \
                .aggregate(s=Sum('reimbursed_amount'))['s'] or 0
        data['family'] = {
            'policy_id': m.policy_id, 'principal_id': principal['id'] if principal else None,
            'reimbursed': _money(family_total), 'own_reimbursed': _money(own),
            'share': round(float(own) / float(family_total), 4) if family_total else None,
        }
        families.append(data)
    activity['top_partners'] = _top(claims, 'partner_id', 'partner__name')
    return {
        'period': period.as_json(),
        'insured': {'id': insured.id, 'name': insured.name, 'other_names': insured.other_names or [],
                    'card_number': insured.card_number, 'country': insured.country.name,
                    'deduced': insured.is_deduced},
        'memberships': families,
        **activity,
    }


def insured_claims(insured_id, params):
    period = Period(params)
    claims = ind.in_period(Claim.objects.filter(insured_id=insured_id), period.start, period.end)
    return {'period': period.as_json(), **_claims_page(claims, params, with_insured=False)}


# ------------------------------------------------------------------ prestataires
def partner_directory(country_id, params):
    period = Period(params)
    partners = Partner.objects.filter(country_id=country_id)
    search = (params.get('search') or '').strip()
    if search:
        partners = partners.filter(name__icontains=search)
    in_period = Q(claims__settlement_date__range=(period.start, period.end))
    partners = partners.annotate(
        claims_count=Count('claims', filter=in_period),
        insureds_count=Count('claims__insured', filter=in_period, distinct=True),
        claimed=Sum('claims__claimed_amount', filter=in_period),
        reimbursed=Sum('claims__reimbursed_amount', filter=in_period),
    )
    if params.get('active', '1') in ('1', 'true'):
        partners = partners.filter(claims_count__gt=0)
    order = {'name': ('name',), '-claims': ('-claims_count', 'name')}.get(params.get('sort'))
    partners = partners.order_by(*order) if order else partners.order_by(F('reimbursed').desc(nulls_last=True), 'name')
    page, meta = _paginate(partners, params)
    results = [{
        'id': p.id, 'name': p.name, 'claims': p.claims_count, 'insureds': p.insureds_count,
        'claimed': _money(p.claimed), 'reimbursed': _money(p.reimbursed), 'reimbursement_rate': _rate(p.reimbursed, p.claimed),
    } for p in page]
    return {**meta, 'period': period.as_json(), 'results': results}


def partner_sheet(partner_id, params):
    period = Period(params)
    partner = Partner.objects.select_related('country').get(id=partner_id)
    activity, claims = _claim_activity(Claim.objects.filter(partner_id=partner_id), period)
    activity['top_employers'] = _top(claims.exclude(employer_id__isnull=True), 'employer_id', 'employer__name')
    activity['top_insureds'] = _top(claims, 'insured_id', 'insured__name')
    return {
        'period': period.as_json(),
        'partner': {'id': partner.id, 'name': partner.name, 'address': partner.address, 'contact': partner.contact,
                    'responsible': partner.main_responsible_name, 'country': partner.country.name},
        **activity,
    }


def partner_claims(partner_id, params):
    period = Period(params)
    claims = ind.in_period(Claim.objects.filter(partner_id=partner_id), period.start, period.end)
    return {'period': period.as_json(), **_claims_page(claims, params)}


# ------------------------------------------------------------------ opérateurs (lignes traitées)
def _lines_in(lines, start, end):
    return lines.filter(claim__settlement_date__range=(start, end))


def _line_values(lines):
    agg = lines.aggregate(claimed=Sum('claimed_amount'), reimbursed=Sum('reimbursed_amount'), n=Count('id'),
                          claims=Count('claim_id', distinct=True), partners=Count('claim__partner_id', distinct=True),
                          insureds=Count('claim__insured_id', distinct=True))
    return {'lines': agg['n'], 'claims': agg['claims'], 'partners': agg['partners'], 'insureds': agg['insureds'],
            'claimed': _money(agg['claimed']), 'reimbursed': _money(agg['reimbursed'])}


def operator_directory(country_id, params):
    period = Period(params)
    country_lines = _lines_in(ClaimLine.objects.filter(claim__country_id=country_id), period.start, period.end)
    total_lines = country_lines.count()
    operators = Operator.objects.filter(country_id=country_id)
    search = (params.get('search') or '').strip()
    if search:
        operators = operators.filter(name__icontains=search)
    in_period = Q(claim_lines__claim__settlement_date__range=(period.start, period.end))
    operators = operators.annotate(
        lines_count=Count('claim_lines', filter=in_period),
        claims_count=Count('claim_lines__claim', filter=in_period, distinct=True),
        partners_count=Count('claim_lines__claim__partner', filter=in_period, distinct=True),
        insureds_count=Count('claim_lines__claim__insured', filter=in_period, distinct=True),
        claimed=Sum('claim_lines__claimed_amount', filter=in_period),
        reimbursed=Sum('claim_lines__reimbursed_amount', filter=in_period),
    )
    if params.get('active', '1') in ('1', 'true'):
        operators = operators.filter(lines_count__gt=0)
    order = {'name': ('name',), '-reimbursed': ('-reimbursed', 'name')}.get(params.get('sort'), ('-lines_count', 'name'))
    page, meta = _paginate(operators.order_by(*order), params)
    results = [{
        'id': o.id, 'name': o.name, 'lines': o.lines_count, 'claims': o.claims_count, 'partners': o.partners_count,
        'insureds': o.insureds_count, 'claimed': _money(o.claimed), 'reimbursed': _money(o.reimbursed),
        'share': round(o.lines_count / total_lines, 4) if total_lines else None,
    } for o in page]
    unassigned = country_lines.filter(operator__isnull=True).count()
    summary = {'total_lines': total_lines, 'unassigned_lines': unassigned,
               'operators': operators.count() if params.get('active', '1') in ('1', 'true') else None}
    return {**meta, 'period': period.as_json(), 'summary': summary, 'results': results}


def operator_sheet(operator_id, params):
    period = Period(params)
    operator = Operator.objects.select_related('country').get(id=operator_id)
    scope = ClaimLine.objects.filter(operator_id=operator_id)
    lines = _lines_in(scope, period.start, period.end)
    current = _line_values(lines)
    previous = _line_values(_lines_in(scope, *period.previous))
    country_lines = _lines_in(ClaimLine.objects.filter(claim__country_id=operator.country_id), period.start, period.end).count()
    current['share'] = round(current['lines'] / country_lines, 4) if country_lines else None
    current['reimbursement_rate'] = _rate(current['reimbursed'], current['claimed'])
    by_tranche = lines.annotate(period=period.trunc('claim__settlement_date')).values('period')
    lines_series = ind.fill_zero(period.periods, list(by_tranche.annotate(value=Count('id')).order_by('period')))
    reimbursed_series = ind.fill_zero(period.periods, [
        {'period': r['period'], 'value': float(r['value'] or 0)}
        for r in by_tranche.annotate(value=Sum('reimbursed_amount')).order_by('period')])
    by_category = (lines.values('category__label').annotate(count=Count('id'), reimbursed=Sum('reimbursed_amount'))
                   .order_by('-count'))
    by_partner = (lines.values('claim__partner_id', 'claim__partner__name')
                  .annotate(count=Count('id'), reimbursed=Sum('reimbursed_amount')).order_by('-count')[:TOP])
    return {
        'period': period.as_json(),
        'operator': {'id': operator.id, 'name': operator.name, 'country': operator.country.name},
        'kpis': current,
        'evolution': {key: ind.evolution(current[key], previous[key])
                      for key in ('lines', 'claims', 'claimed', 'reimbursed', 'partners', 'insureds')},
        'previous': previous,
        'lines_series': serie_to_pairs(lines_series),
        'reimbursed_series': serie_to_pairs(reimbursed_series),
        'by_category': [{'label': r['category__label'] or '—', 'count': r['count'], 'reimbursed': _money(r['reimbursed'])}
                        for r in by_category],
        'by_partner': [{'id': r['claim__partner_id'], 'label': r['claim__partner__name'], 'count': r['count'],
                        'reimbursed': _money(r['reimbursed'])} for r in by_partner],
    }


def operator_lines(operator_id, params):
    period = Period(params)
    lines = (_lines_in(ClaimLine.objects.filter(operator_id=operator_id), period.start, period.end)
             .select_related('claim__insured', 'claim__partner', 'claim__policy', 'act', 'category', 'invoice', 'operator')
             .order_by('-claim__settlement_date', 'claim_id', 'line_number'))
    page, meta = _paginate(lines, params)
    results = []
    for line in page:
        row = _line_json(line)
        c = line.claim
        row['claim'] = {'id': c.id, 'number': c.number, 'claim_date': _date(c.claim_date),
                        'settlement_date': _date(c.settlement_date)}
        row['insured'] = {'id': c.insured_id, 'name': c.insured.name}
        row['partner'] = {'id': c.partner_id, 'name': c.partner.name}
        row['policy'] = {'id': c.policy_id, 'number': c.policy.policy_number}
        results.append(row)
    return {**meta, 'period': period.as_json(), 'results': results}
