"""
Familles d'assurés (lot F1, décisions du 09/10/2026).

Une famille = un assuré principal **sur une police** et ses bénéficiaires (conjoints, enfants) sur cette même police :
adhésions (InsuredEmployer) de rôle « primary », et adhésions dont `primary_insured_ref` est ce principal.
Une même personne principale sur deux polices (CEET puis CEET retraités) a donc deux familles.

Lecture : liste des familles d'un pays, fiche d'une famille (membres, consommation, sinistres).
Corrections (mot de passe vérifié par la vue, chacune tracée dans FamilyChange) : rattacher un bénéficiaire à un autre
principal, changer un rôle, fusionner deux fiches qui sont la même personne, choisir le nom retenu.
Les corrections ne sont pas défaites par un nouvel import : l'import ne modifie ni le rôle ni le principal d'une
adhésion existante, et retrouve une personne par son nom retenu ou ses autres écritures.
"""
from collections import defaultdict
from datetime import date

from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth

from core.models import (
    Claim, ClaimLine, FamilyChange, Insured, InsuredEmployer, Policy, Client, Subscriber,
)
from importer.reconciliation.normalize import clean_text, name_key, text_key

ROLE_LABELS = dict(InsuredEmployer.ROLE_CHOICES)
DEPENDENT_ROLES = ('spouse', 'child', 'other')
ROLES = ('primary',) + DEPENDENT_ROLES


class FamilyError(Exception):
    """Correction refusée : le message (en français) est renvoyé tel quel à l'utilisateur."""


def parse_period(start, end):
    """Dates « AAAA-MM-JJ » facultatives ; ValueError si l'une est mal écrite ou si début > fin."""
    def parse(value, label):
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            raise ValueError(f"Date de {label} invalide : « {value} » (format attendu AAAA-MM-JJ).")
    d1, d2 = parse(start, 'début'), parse(end, 'fin')
    if d1 and d2 and d1 > d2:
        raise ValueError("La date de début est postérieure à la date de fin.")
    return d1, d2


def _in_period(qs, start, end, field='settlement_date'):
    if start:
        qs = qs.filter(**{f'{field}__date__gte': start})
    if end:
        qs = qs.filter(**{f'{field}__date__lte': end})
    return qs


def _rate(value):
    return float(value) if value is not None else None


def _money(value):
    return round(float(value or 0), 2)


def _family_claims(country, policy_id, principal_id):
    """Sinistres d'une famille : ceux du principal et de ses bénéficiaires, sur la police."""
    return Claim.objects.filter(country=country, policy_id=policy_id).filter(
        Q(membership__role='primary', insured_id=principal_id) | Q(membership__primary_insured_ref_id=principal_id))


# --------------------------------------------------------------------------------------------- lecture
def filter_options(country):
    policies = Policy.objects.filter(country=country).order_by('policy_number')
    employers = Client.objects.filter(country=country, policies__isnull=False).distinct().order_by('name')
    return {
        'policies': [{'id': p.id, 'number': p.policy_number} for p in policies],
        'employers': [{'id': e.id, 'name': e.name} for e in employers],
        'currency': country.currency_code,
    }


def _name_filter(qs, search, prefix=''):
    """Recherche par nom (sans accents ni casse, mots dans n'importe quel ordre) ou par n° de carte."""
    words = name_key(search).split()
    cond = Q()
    for word in words:
        cond &= Q(**{f'{prefix}name_key__contains': word})
    raw = clean_text(search) or ''
    return qs.filter(cond | Q(**{f'{prefix}card_number__iexact': raw}))


def list_families(country, search='', policy_id=None, employer_id=None, start=None, end=None,
                  ordering='name', page=1, page_size=25):
    principals = (InsuredEmployer.objects.filter(policy__country=country, role='primary')
                  .select_related('insured', 'policy', 'employer', 'plan'))
    if policy_id:
        principals = principals.filter(policy_id=policy_id)
    if employer_id:
        principals = principals.filter(employer_id=employer_id)

    dependents = InsuredEmployer.objects.filter(policy__country=country).exclude(role='primary')
    if search:
        # Une famille ressort si son principal ou l'un de ses bénéficiaires correspond
        found = _name_filter(Insured.objects.filter(country=country), search).values('pk')
        via_dep = dependents.filter(insured__in=found).values_list('policy_id', 'primary_insured_ref_id')
        dep_pairs = set(via_dep)
        direct = set(principals.filter(insured__in=found).values_list('policy_id', 'insured_id'))
        keep = direct | dep_pairs
        principals = [m for m in principals if (m.policy_id, m.insured_id) in keep]

    # Une famille par (police, principal) ; un principal chez deux employeurs de la même police reste une famille
    families = {}
    for m in principals:
        key = (m.policy_id, m.insured_id)
        f = families.get(key)
        if f is None:
            plan_rate = m.plan.coverage_rate if m.plan_id else None
            f = families[key] = {
                'policy_id': m.policy_id, 'policy_number': m.policy.policy_number,
                'principal_id': m.insured_id, 'principal_name': m.insured.name,
                'card_number': m.insured.card_number, 'is_deduced': m.insured.is_deduced,
                'employers': [], 'plan': m.plan.label if m.plan_id else None,
                'coverage_rate': _rate(plan_rate if plan_rate is not None else m.policy.coverage_rate),
                'spouses': 0, 'children': 0, 'others': 0, 'members': 1,
                'claims_count': 0, 'claimed_amount': 0.0, 'reimbursed_amount': 0.0,
                'first_consumption': None, 'last_consumption': None,
            }
        name = m.employer.name if m.employer_id else 'Particulier'
        if name not in f['employers']:
            f['employers'].append(name)

    counts = (dependents.filter(policy_id__in={k[0] for k in families})
              .values('policy_id', 'primary_insured_ref_id', 'role').annotate(n=Count('insured', distinct=True)))
    field = {'spouse': 'spouses', 'child': 'children', 'other': 'others'}
    for row in counts:
        f = families.get((row['policy_id'], row['primary_insured_ref_id']))
        if f:
            f[field[row['role']]] += row['n']
            f['members'] += row['n']

    claims = _in_period(Claim.objects.filter(country=country, policy_id__in={k[0] for k in families}), start, end)
    rows = (claims.annotate(family=Coalesce('membership__primary_insured_ref_id', 'insured_id'))
            .values('policy_id', 'family')
            .annotate(n=Count('id'), claimed=Sum('claimed_amount'), reimbursed=Sum('reimbursed_amount'),
                      first=Min('settlement_date'), last=Max('settlement_date')))
    for row in rows:
        f = families.get((row['policy_id'], row['family']))
        if f:
            f.update(claims_count=row['n'], claimed_amount=_money(row['claimed']),
                     reimbursed_amount=_money(row['reimbursed']),
                     first_consumption=row['first'].date().isoformat() if row['first'] else None,
                     last_consumption=row['last'].date().isoformat() if row['last'] else None)

    result = list(families.values())
    sorts = {
        'name': lambda f: (text_key(f['principal_name']), f['policy_number']),
        'policy': lambda f: (f['policy_number'], text_key(f['principal_name'])),
        '-reimbursed': lambda f: (-f['reimbursed_amount'], text_key(f['principal_name'])),
        '-members': lambda f: (-f['members'], text_key(f['principal_name'])),
        '-claims': lambda f: (-f['claims_count'], text_key(f['principal_name'])),
    }
    result.sort(key=sorts.get(ordering, sorts['name']))

    total = len(result)
    page_size = max(1, min(int(page_size), 200))
    page = max(1, int(page))
    chunk = result[(page - 1) * page_size: page * page_size]
    return {
        'count': total, 'page': page, 'page_size': page_size,
        'totals': {
            'families': total,
            'members': sum(f['members'] for f in result),
            'claimed_amount': _money(sum(f['claimed_amount'] for f in result)),
            'reimbursed_amount': _money(sum(f['reimbursed_amount'] for f in result)),
        },
        'currency': country.currency_code,
        'results': chunk,
    }


def _principal_memberships(country, policy_id, principal_id):
    return list(InsuredEmployer.objects.filter(policy__country=country, policy_id=policy_id, insured_id=principal_id,
                                               role='primary').select_related('insured', 'policy', 'employer', 'plan',
                                                                              'policy__subscriber'))


def family_exists(country, policy_id, principal_id):
    return InsuredEmployer.objects.filter(policy__country=country, policy_id=policy_id, insured_id=principal_id,
                                          role='primary').exists()


def family_detail(country, policy_id, principal_id, start=None, end=None):
    """Fiche d'une famille, ou None si ce principal n'a pas de famille sur cette police (dans ce pays)."""
    heads = _principal_memberships(country, policy_id, principal_id)
    if not heads:
        return None
    policy = heads[0].policy
    principal = heads[0].insured
    deps = list(InsuredEmployer.objects.filter(policy_id=policy_id, primary_insured_ref_id=principal_id)
                .exclude(role='primary').select_related('insured', 'employer', 'plan'))

    claims = _in_period(_family_claims(country, policy_id, principal_id), start, end)
    per_member = {r['insured_id']: r for r in claims.values('insured_id').annotate(
        n=Count('id'), claimed=Sum('claimed_amount'), reimbursed=Sum('reimbursed_amount'),
        first=Min('settlement_date'), last=Max('settlement_date'))}

    members = {}
    for m in heads + deps:
        ins = m.insured
        e = members.get(ins.pk)
        if e is None:
            stats = per_member.get(ins.pk, {})
            e = members[ins.pk] = {
                'insured_id': ins.pk, 'name': ins.name, 'other_names': ins.other_names,
                'card_number': ins.card_number, 'birth_date': ins.birth_date.isoformat() if ins.birth_date else None,
                'is_deduced': ins.is_deduced, 'role': m.role, 'role_label': ROLE_LABELS.get(m.role, m.role),
                'employers': [], 'plans': [], 'start_date': None, 'end_date': None,
                'claims_count': stats.get('n', 0), 'claimed_amount': _money(stats.get('claimed')),
                'reimbursed_amount': _money(stats.get('reimbursed')),
                'first_consumption': stats['first'].date().isoformat() if stats.get('first') else None,
                'last_consumption': stats['last'].date().isoformat() if stats.get('last') else None,
                'other_policies': 0,
            }
        emp = m.employer.name if m.employer_id else 'Particulier'
        if emp not in e['employers']:
            e['employers'].append(emp)
        if m.plan_id and m.plan.label not in e['plans']:
            e['plans'].append(m.plan.label)
        if m.start_date and (not e['start_date'] or m.start_date.isoformat() < e['start_date']):
            e['start_date'] = m.start_date.isoformat()
        if m.end_date and (not e['end_date'] or m.end_date.isoformat() > e['end_date']):
            e['end_date'] = m.end_date.isoformat()

    # Autres polices sur lesquelles la personne figure (une famille par police)
    for row in (InsuredEmployer.objects.filter(insured_id__in=members).exclude(policy_id=policy_id)
                .values('insured_id').annotate(n=Count('policy', distinct=True))):
        members[row['insured_id']]['other_policies'] = row['n']

    order = {'primary': 0, 'spouse': 1, 'child': 2, 'other': 3}
    member_list = sorted(members.values(), key=lambda e: (order.get(e['role'], 9), text_key(e['name'])))

    lines = ClaimLine.objects.filter(claim__in=claims)
    by_category = [
        {'category': r['category__label'], 'lines': r['n'], 'claimed_amount': _money(r['claimed']),
         'reimbursed_amount': _money(r['reimbursed'])}
        for r in lines.values('category__label').annotate(n=Count('id'), claimed=Sum('claimed_amount'),
                                                         reimbursed=Sum('reimbursed_amount'))
        .order_by('-reimbursed')
    ]
    monthly = [
        {'month': r['month'].date().isoformat()[:7], 'claims': r['n'], 'claimed_amount': _money(r['claimed']),
         'reimbursed_amount': _money(r['reimbursed'])}
        for r in claims.annotate(month=TruncMonth('settlement_date')).values('month')
        .annotate(n=Count('id'), claimed=Sum('claimed_amount'), reimbursed=Sum('reimbursed_amount')).order_by('month')
    ]
    totals = claims.aggregate(n=Count('id'), claimed=Sum('claimed_amount'), reimbursed=Sum('reimbursed_amount'))

    plan = next((m.plan for m in heads if m.plan_id), None)
    rate = plan.coverage_rate if plan and plan.coverage_rate is not None else policy.coverage_rate
    history = FamilyChange.objects.filter(country=country, policy_id=policy_id, principals__contains=[principal_id])
    return {
        'policy': {'id': policy.id, 'number': policy.policy_number,
                   'subscriber': policy.subscriber.name if policy.subscriber_id else None,
                   'coverage_rate': _rate(rate), 'plan': plan.label if plan else None},
        'principal': {'id': principal.id, 'name': principal.name, 'is_deduced': principal.is_deduced},
        'employers': sorted({m.employer.name if m.employer_id else 'Particulier' for m in heads}),
        'currency': country.currency_code,
        'period': {'start': start.isoformat() if start else None, 'end': end.isoformat() if end else None},
        'members': member_list,
        'totals': {'members': len(member_list), 'claims_count': totals['n'] or 0,
                   'claimed_amount': _money(totals['claimed']), 'reimbursed_amount': _money(totals['reimbursed'])},
        'by_category': by_category,
        'monthly': monthly,
        'history': [_change_json(c) for c in history[:100]],
    }


def _change_json(c):
    return {'id': c.id, 'action': c.action, 'action_label': c.get_action_display(), 'summary': c.summary,
            'user': c.user_name, 'date': c.created_at.isoformat()}


def family_claims(country, policy_id, principal_id, start=None, end=None, member_id=None, page=1, page_size=20):
    claims = _in_period(_family_claims(country, policy_id, principal_id), start, end)
    if member_id:
        claims = claims.filter(insured_id=member_id)
    claims = claims.select_related('insured', 'partner', 'membership').order_by('-settlement_date', '-id')
    total = claims.count()
    page_size = max(1, min(int(page_size), 100))
    page = max(1, int(page))
    chunk = list(claims[(page - 1) * page_size: page * page_size])
    lines = defaultdict(list)
    for line in (ClaimLine.objects.filter(claim__in=chunk).select_related('category', 'act')
                 .order_by('claim_id', 'line_number')):
        lines[line.claim_id].append({
            'category': line.category.label, 'act': line.act.label if line.act_id else None,
            'guarantee': line.guarantee_label, 'status': line.status,
            'settlement_date': line.settlement_date.isoformat(),
            'claimed_amount': _money(line.claimed_amount), 'reimbursed_amount': _money(line.reimbursed_amount),
        })
    return {
        'count': total, 'page': page, 'page_size': page_size, 'currency': country.currency_code,
        'results': [{
            'id': c.id, 'number': c.number, 'status': c.status, 'status_label': c.get_status_display(),
            'claim_date': c.claim_date.date().isoformat() if c.claim_date else None,
            'settlement_date': c.settlement_date.date().isoformat(),
            'insured_id': c.insured_id, 'insured_name': c.insured.name,
            'role_label': ROLE_LABELS.get(c.membership.role, c.membership.role),
            'partner': c.partner.name,
            'claimed_amount': _money(c.claimed_amount), 'reimbursed_amount': _money(c.reimbursed_amount),
            'lines': lines.get(c.id, []),
        } for c in chunk],
    }


def principal_choices(country, policy_id, search='', exclude=None, limit=20):
    """Principaux d'une police (cible d'un rattachement)."""
    qs = Insured.objects.filter(country=country, insured_clients__policy_id=policy_id,
                                insured_clients__role='primary').distinct()
    if exclude:
        qs = qs.exclude(pk=exclude)
    if search:
        qs = _name_filter(qs, search)
    return [{'id': i.id, 'name': i.name, 'card_number': i.card_number, 'is_deduced': i.is_deduced}
            for i in qs.order_by('name')[:limit]]


def insured_choices(country, search, exclude=None, limit=20):
    """Assurés du pays (candidats à une fusion), avec leurs adhésions pour les distinguer."""
    if not search:
        return []
    qs = _name_filter(Insured.objects.filter(country=country), search)
    if exclude:
        qs = qs.exclude(pk=exclude)
    people = list(qs.order_by('name')[:limit])
    links = defaultdict(list)
    for m in (InsuredEmployer.objects.filter(insured__in=people)
              .select_related('policy', 'primary_insured_ref')):
        links[m.insured_id].append({
            'policy_id': m.policy_id, 'policy_number': m.policy.policy_number, 'role': m.role,
            'role_label': ROLE_LABELS.get(m.role, m.role),
            'principal': m.primary_insured_ref.name if m.primary_insured_ref_id else None,
        })
    return [{'id': i.id, 'name': i.name, 'card_number': i.card_number, 'is_deduced': i.is_deduced,
             'other_names': i.other_names, 'memberships': links.get(i.id, [])} for i in people]


# --------------------------------------------------------------------------------------------- corrections
def _user_name(user):
    full = f'{user.first_name} {user.last_name}'.strip()
    return full or user.username


def _log(country, user, action, summary, policy=None, insured=None, principals=(), details=None):
    return FamilyChange.objects.create(
        country=country, policy=policy, insured=insured, action=action, summary=summary,
        principals=sorted({p for p in principals if p}), details=details or {},
        user=user, user_name=_user_name(user))


def _insured(country, insured_id, label='Assuré'):
    ins = Insured.objects.select_for_update().filter(country=country, pk=insured_id).first()
    if ins is None:
        raise FamilyError(f"{label} introuvable dans votre pays.")
    return ins


def _policy(country, policy_id):
    policy = Policy.objects.filter(country=country, pk=policy_id).first()
    if policy is None:
        raise FamilyError("Police introuvable dans votre pays.")
    return policy


def _require_principal(policy, insured_id):
    principal = Insured.objects.filter(pk=insured_id, insured_clients__policy=policy,
                                       insured_clients__role='primary').first()
    if principal is None:
        raise FamilyError(f"La personne choisie n'est pas assuré principal sur la police {policy.policy_number}.")
    return principal


@transaction.atomic
def attach_member(country, user, policy_id, insured_id, principal_id):
    """Rattache un bénéficiaire (toutes ses adhésions sur la police) à un autre assuré principal de la police."""
    policy = _policy(country, policy_id)
    ins = _insured(country, insured_id)
    links = list(InsuredEmployer.objects.select_for_update().filter(policy=policy, insured=ins))
    if not links:
        raise FamilyError(f"{ins.name} ne figure pas sur la police {policy.policy_number}.")
    if any(m.role == 'primary' for m in links):
        raise FamilyError(f"{ins.name} est assuré principal sur cette police : changez d'abord son rôle.")
    if int(principal_id) == ins.pk:
        raise FamilyError("Un bénéficiaire ne peut pas être rattaché à lui-même.")
    target = _require_principal(policy, principal_id)
    old_ids = {m.primary_insured_ref_id for m in links}
    if old_ids == {target.pk}:
        raise FamilyError(f"{ins.name} est déjà rattaché à {target.name}.")
    old = Insured.objects.filter(pk__in=old_ids)
    old_names = ', '.join(o.name for o in old) or '—'
    InsuredEmployer.objects.filter(pk__in=[m.pk for m in links]).update(primary_insured_ref=target)
    _log(country, user, FamilyChange.Action.ATTACH,
         f"{ins.name} ({ROLE_LABELS.get(links[0].role)}) rattaché à {target.name} (avant : {old_names}).",
         policy=policy, insured=ins, principals=list(old_ids) + [target.pk],
         details={'from': sorted(old_ids), 'to': target.pk})
    return {'detail': f"{ins.name} est maintenant rattaché à la famille de {target.name}.",
            'family': {'policy_id': policy.pk, 'principal_id': target.pk}}


@transaction.atomic
def change_role(country, user, policy_id, insured_id, role, principal_id=None):
    """Change le rôle d'une personne sur la police (toutes ses adhésions sur cette police).
    - devenir principal : la personne forme sa propre famille ;
    - un principal qui devient conjoint / enfant : `principal_id` obligatoire, et il ne doit plus avoir de
      bénéficiaires (à rattacher d'abord) ;
    - conjoint <-> enfant : le principal ne change pas, sauf si `principal_id` est donné."""
    if role not in ROLES:
        raise FamilyError("Rôle inconnu : choisissez assuré principal, conjoint(e), enfant ou autre.")
    policy = _policy(country, policy_id)
    ins = _insured(country, insured_id)
    links = list(InsuredEmployer.objects.select_for_update().filter(policy=policy, insured=ins))
    if not links:
        raise FamilyError(f"{ins.name} ne figure pas sur la police {policy.policy_number}.")
    current = links[0].role
    was_primary = any(m.role == 'primary' for m in links)
    old_principals = {m.primary_insured_ref_id for m in links if m.primary_insured_ref_id}

    if role == 'primary':
        if was_primary and all(m.role == 'primary' for m in links):
            raise FamilyError(f"{ins.name} est déjà assuré principal sur cette police.")
        InsuredEmployer.objects.filter(pk__in=[m.pk for m in links]).update(role='primary', primary_insured_ref=None)
        summary = (f"{ins.name} : {ROLE_LABELS.get(current)} -> assuré principal "
                   f"(n'est plus rattaché à {', '.join(Insured.objects.filter(pk__in=old_principals).values_list('name', flat=True)) or '—'}).")
        family = {'policy_id': policy.pk, 'principal_id': ins.pk}
        principals = list(old_principals) + [ins.pk]
    else:
        if was_primary:
            if not principal_id:
                raise FamilyError(f"Choisissez l'assuré principal auquel rattacher {ins.name}.")
            n = (InsuredEmployer.objects.filter(policy=policy, primary_insured_ref=ins).exclude(role='primary')
                 .values('insured').distinct().count())
            if n:
                raise FamilyError(f"{ins.name} a encore {n} bénéficiaire(s) sur cette police : rattachez-les d'abord "
                                  "à un autre assuré principal.")
        if principal_id and int(principal_id) == ins.pk:
            raise FamilyError("Une personne ne peut pas être son propre assuré principal.")
        target = _require_principal(policy, principal_id) if principal_id else None
        if target is None and len(old_principals) != 1:
            raise FamilyError(f"Choisissez l'assuré principal auquel rattacher {ins.name}.")
        target_id = target.pk if target else next(iter(old_principals))
        if not was_primary and current == role and old_principals == {target_id} and \
                all(m.role == role for m in links):
            raise FamilyError(f"{ins.name} a déjà ce rôle dans cette famille.")
        InsuredEmployer.objects.filter(pk__in=[m.pk for m in links]).update(role=role, primary_insured_ref_id=target_id)
        target_name = target.name if target else Insured.objects.get(pk=target_id).name
        summary = f"{ins.name} : {ROLE_LABELS.get(current)} -> {ROLE_LABELS.get(role)} de {target_name}."
        family = {'policy_id': policy.pk, 'principal_id': target_id}
        principals = list(old_principals) + [target_id] + ([ins.pk] if was_primary else [])

    _log(country, user, FamilyChange.Action.ROLE, summary, policy=policy, insured=ins, principals=principals,
         details={'from_role': current, 'to_role': role, 'from_principals': sorted(old_principals)})
    return {'detail': summary, 'family': family,
            'moved': {'from': ins.pk, 'to': family['principal_id']} if was_primary and role != 'primary' else None}


@transaction.atomic
def merge_insureds(country, user, keep_id, absorb_id):
    """Fusionne deux fiches qui sont la même personne : `absorb` disparaît, ses adhésions, sinistres, bénéficiaires
    et écritures de nom passent sur `keep`. Refusé si les deux fiches ont des n° de carte différents, ou des rôles
    incompatibles sur une même adhésion (police + employeur)."""
    if int(keep_id) == int(absorb_id):
        raise FamilyError("Choisissez deux fiches différentes.")
    keep = _insured(country, keep_id, 'Fiche à conserver')
    absorb = _insured(country, absorb_id, 'Fiche à fusionner')
    if keep.card_number and absorb.card_number and keep.card_number != absorb.card_number:
        raise FamilyError(f"Les deux fiches ont des identifiants différents ({keep.card_number} et "
                          f"{absorb.card_number}) : ce sont deux personnes pour l'assureur, fusion refusée.")

    keep_links = {(m.policy_id, m.employer_id): m for m in
                  InsuredEmployer.objects.select_for_update().filter(insured=keep)}
    absorb_links = list(InsuredEmployer.objects.select_for_update().filter(insured=absorb).select_related('policy'))
    for m in absorb_links + list(keep_links.values()):
        other = absorb if m.insured_id == keep.pk else keep
        if m.primary_insured_ref_id == other.pk:
            raise FamilyError(f"{m.insured.name} est bénéficiaire de {other.name} sur la police "
                              f"{m.policy.policy_number} : une personne ne peut pas être son propre bénéficiaire.")
    for m in absorb_links:
        k = keep_links.get((m.policy_id, m.employer_id))
        if k and (k.role != m.role or k.primary_insured_ref_id != m.primary_insured_ref_id):
            raise FamilyError(f"Sur la police {m.policy.policy_number}, les deux fiches n'ont pas le même rôle ou "
                              "pas le même principal : corrigez d'abord le rôle ou le rattachement.")

    principals = set()
    moved_links = merged_links = 0
    for m in absorb_links:
        principals.add(m.insured_id if m.role == 'primary' else m.primary_insured_ref_id)
        k = keep_links.get((m.policy_id, m.employer_id))
        if k is None:
            m.insured = keep
            m.save(update_fields=['insured'])
            moved_links += 1
            continue
        Claim.objects.filter(membership=m).update(membership=k)
        if m.start_date and (not k.start_date or m.start_date < k.start_date):
            k.start_date = m.start_date
        if m.end_date and (not k.end_date or m.end_date > k.end_date):
            k.end_date = m.end_date
        if not k.plan_id and m.plan_id:
            k.plan_id = m.plan_id
        k.save(update_fields=['start_date', 'end_date', 'plan'])
        m.delete()
        merged_links += 1
    for m in keep_links.values():
        principals.add(m.insured_id if m.role == 'primary' else m.primary_insured_ref_id)
    principals.discard(absorb.pk)
    principals.add(keep.pk)

    claims_moved = Claim.objects.filter(insured=absorb).update(insured=keep)
    dependents_moved = InsuredEmployer.objects.filter(primary_insured_ref=absorb).update(primary_insured_ref=keep)
    Subscriber.objects.filter(insured=absorb).update(insured=keep)

    names = set(keep.other_names) | set(absorb.other_names) | {absorb.name}
    names.discard(keep.name)
    keep.other_names = sorted(names)
    card = absorb.card_number
    if card and not keep.card_number:
        absorb.card_number = None
        absorb.save(update_fields=['card_number'])
        keep.card_number = card
    keep.is_deduced = keep.is_deduced and absorb.is_deduced
    for field in ('birth_date', 'phone_number', 'email'):
        if not getattr(keep, field) and getattr(absorb, field):
            setattr(keep, field, getattr(absorb, field))
    keep.save()

    summary = (f"Fiche « {absorb.name} » fusionnée dans « {keep.name} » : {claims_moved} sinistre(s), "
               f"{moved_links + merged_links} adhésion(s), {dependents_moved} bénéficiaire(s) repris.")
    details = {'absorbed': {'id': absorb.pk, 'name': absorb.name, 'card_number': card,
                            'other_names': absorb.other_names},
               'claims_moved': claims_moved, 'memberships_moved': moved_links, 'memberships_merged': merged_links,
               'dependents_moved': dependents_moved}
    # Les anciennes corrections qui visaient la fiche absorbée restent visibles depuis la famille conservée
    for change in FamilyChange.objects.filter(country=country, principals__contains=[absorb.pk]):
        change.principals = sorted((set(change.principals) - {absorb.pk}) | {keep.pk})
        change.save(update_fields=['principals'])
    FamilyChange.objects.filter(insured=absorb).update(insured=keep)
    policies = {m.policy_id for m in absorb_links} | {p for p, _ in keep_links}
    absorb.delete()
    for policy_id in sorted(policies) or [None]:
        _log(country, user, FamilyChange.Action.MERGE, summary, policy=Policy.objects.filter(pk=policy_id).first(),
             insured=keep, principals=principals, details=details)
    return {'detail': summary, 'moved': {'from': details['absorbed']['id'], 'to': keep.pk}}


@transaction.atomic
def rename_insured(country, user, insured_id, name, policy_id=None):
    """Nom retenu : choisi parmi les écritures connues de la personne (nom actuel et autres écritures)."""
    ins = _insured(country, insured_id)
    wanted = clean_text(name)
    if not wanted:
        raise FamilyError("Choisissez le nom à retenir.")
    known = [ins.name] + list(ins.other_names)
    if wanted not in known:
        raise FamilyError("Le nom retenu doit être l'une des écritures connues de cette personne.")
    if wanted == ins.name:
        raise FamilyError(f"« {wanted} » est déjà le nom retenu.")
    old = ins.name
    ins.other_names = sorted((set(ins.other_names) | {old}) - {wanted})
    ins.name, ins.name_key = wanted, name_key(wanted)
    ins.save(update_fields=['name', 'name_key', 'other_names', 'modification_date'])

    links = InsuredEmployer.objects.filter(insured=ins)
    principals = {m.insured_id if m.role == 'primary' else m.primary_insured_ref_id for m in links}
    policies = sorted({m.policy_id for m in links}) or [None]
    summary = f"Nom retenu : « {wanted} » (au lieu de « {old} »)."
    for pid in policies:
        _log(country, user, FamilyChange.Action.RENAME, summary, policy=Policy.objects.filter(pk=pid).first(),
             insured=ins, principals=principals, details={'from': old, 'to': wanted})
    return {'detail': summary}
