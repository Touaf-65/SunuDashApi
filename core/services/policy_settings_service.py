"""
Paramétrage des polices (lot I4, décision I du 09/10/2026) : taux de couverture et souscripteur.

- Le taux est saisi par l'admin territorial, sur la police et sur chacun de ses plans de garanties ; il est
  pré-rempli par le **taux observé** à l'import (rapport remboursé / réclamé le plus fréquent sur les lignes d'actes).
  Un taux saisi (MANUAL) n'est jamais remplacé par un import ; « revenir au taux observé » le rend à nouveau
  automatique.
- Le souscripteur est déduit à l'import quand c'est possible (entreprise : employeur unique ou nom commun ;
  particulier : principal unique) ; sinon il est à renseigner ici.
Chaque modification est tracée (ReferenceChange).
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, FloatField, Q, Sum
from django.db.models.functions import Cast, Round

from core.models import (
    Claim, ClaimLine, GuaranteePlan, InsuredEmployer, Policy, RateSource, ReferenceChange, Subscriber,
)
from importer.reconciliation.normalize import clean_text, text_key


class SettingsError(Exception):
    """Modification refusée : message renvoyé tel quel."""


def _rate(value):
    return float(value) if value is not None else None


def _observed_of(obj, lines):
    """Taux observé enregistré au dernier import ; à défaut (données antérieures), recalculé sur les lignes en base."""
    return _rate(obj.observed_rate) if obj.observed_rate is not None else _observed(lines)


def _observed(lines):
    """Taux observé : rapport remboursé / réclamé (arrondi à 0,01) le plus fréquent, comme à l'import."""
    row = (lines.filter(claimed_amount__gt=0, reimbursed_amount__gt=0)
           .annotate(ratio=Round(Cast('reimbursed_amount', FloatField()) / Cast('claimed_amount', FloatField()), 2))
           .values('ratio').annotate(n=Count('id')).order_by('-n', '-ratio').first())
    return float(row['ratio']) if row else None


def _subscriber_json(sub):
    if sub is None:
        return None
    return {'id': sub.id, 'name': sub.name, 'kind': sub.kind, 'kind_label': sub.get_kind_display()}


def _plans_json(policy):
    plans = list(policy.plans.all().order_by('label'))
    members = dict(InsuredEmployer.objects.filter(plan__in=plans).values('plan').annotate(n=Count('insured', distinct=True))
                   .values_list('plan', 'n'))
    return [{
        'id': p.id, 'label': p.label, 'coverage_rate': _rate(p.coverage_rate), 'source': p.coverage_rate_source,
        'observed_rate': _observed_of(p, ClaimLine.objects.filter(claim__policy=policy, claim__membership__plan=p)),
        'members': members.get(p.id, 0),
    } for p in plans]


def _policy_json(policy, stats=None, with_plans=True):
    stats = stats or {}
    data = {
        'id': policy.id, 'number': policy.policy_number,
        'subscriber': _subscriber_json(policy.subscriber),
        'employers': sorted(e.name for e in policy.employers.all()),
        'coverage_rate': _rate(policy.coverage_rate), 'source': policy.coverage_rate_source,
        'observed_rate': _observed_of(policy, ClaimLine.objects.filter(claim__policy=policy)),
        'members': stats.get('members', 0), 'families': stats.get('families', 0),
        'claims_count': stats.get('claims', 0), 'reimbursed_amount': round(float(stats.get('reimbursed') or 0), 2),
        'plans_count': policy.plans.count(),
    }
    data['to_complete'] = data['subscriber'] is None or data['coverage_rate'] is None
    if with_plans:
        data['plans'] = _plans_json(policy)
    return data


def _stats(country, policy_ids):
    out = {pid: {} for pid in policy_ids}
    for r in (InsuredEmployer.objects.filter(policy_id__in=policy_ids).values('policy_id')
              .annotate(members=Count('insured', distinct=True),
                        families=Count('insured', filter=Q(role='primary'), distinct=True))):
        out[r['policy_id']].update(members=r['members'], families=r['families'])
    for r in (Claim.objects.filter(country=country, policy_id__in=policy_ids).values('policy_id')
              .annotate(claims=Count('id'), reimbursed=Sum('reimbursed_amount'))):
        out[r['policy_id']].update(claims=r['claims'], reimbursed=r['reimbursed'])
    return out


def list_policies(country, search='', to_complete=False):
    qs = Policy.objects.filter(country=country).select_related('subscriber').prefetch_related('employers')
    if search:
        key = text_key(search)
        qs = qs.filter(Q(number_key__icontains=key.replace(' ', '')) | Q(policy_number__icontains=search.strip())
                       | Q(subscriber__name_key__icontains=key) | Q(employers__name_key__icontains=key)).distinct()
    policies = list(qs.order_by('policy_number'))
    stats = _stats(country, [p.id for p in policies])
    rows = [_policy_json(p, stats[p.id], with_plans=False) for p in policies]
    if to_complete:
        rows = [r for r in rows if r['to_complete']]
    return {'currency': country.currency_code, 'results': rows}


def policy_detail(country, policy_id):
    policy = (Policy.objects.filter(country=country, pk=policy_id).select_related('subscriber')
              .prefetch_related('employers').first())
    if policy is None:
        return None
    data = _policy_json(policy, _stats(country, [policy.id])[policy.id])
    history = ReferenceChange.objects.filter(
        Q(object_type='POLICY', object_id=policy.id) | Q(object_type='PLAN', object_id__in=[p['id'] for p in data['plans']]),
        country=country)
    data['history'] = [{'id': h.id, 'summary': h.summary, 'user': h.user_name, 'date': h.created_at.isoformat()}
                       for h in history[:50]]
    return data


def list_subscribers(country, search=''):
    qs = Subscriber.objects.filter(country=country).annotate(n=Count('policies'))
    if search:
        qs = qs.filter(name_key__icontains=text_key(search))
    return [{'id': s.id, 'name': s.name, 'kind': s.kind, 'kind_label': s.get_kind_display(), 'policies': s.n}
            for s in qs.order_by('name')[:50]]


def _parse_rate(value, label):
    """Taux saisi en pourcentage (80 ou « 80,5 ») -> Decimal 0,8050."""
    try:
        pct = Decimal(str(value).replace(',', '.').replace('%', '').strip())
    except (InvalidOperation, ValueError):
        raise SettingsError(f"{label} : taux invalide « {value} ».")
    if pct <= 0 or pct > 100:
        raise SettingsError(f"{label} : le taux doit être compris entre 0 et 100 %.")
    return (pct / 100).quantize(Decimal('0.0001'))


def _pct(rate):
    return '—' if rate is None else f"{(Decimal(rate) * 100).normalize():f} %"


def _user_name(user):
    return f'{user.first_name} {user.last_name}'.strip() or user.username


@transaction.atomic
def update_policy(country, user, policy_id, data):
    """`data` : coverage_rate (en %), reset_rate (revenir au taux observé), plans [{id, coverage_rate | reset}],
    subscriber_id ou subscriber {kind, name}. Renvoie la police à jour."""
    policy = Policy.objects.select_for_update().filter(country=country, pk=policy_id).first()
    if policy is None:
        raise SettingsError("Police introuvable dans votre pays.")
    changes = []

    def log(object_type, object_id, label, summary, details):
        ReferenceChange.objects.create(country=country, object_type=object_type, object_id=object_id, label=label,
                                       summary=summary, details=details, user=user, user_name=_user_name(user))
        changes.append(summary)

    # Taux de la police
    lines = ClaimLine.objects.filter(claim__policy=policy)
    if data.get('reset_rate'):
        observed = _observed_of(policy, lines)
        old = policy.coverage_rate
        policy.coverage_rate = Decimal(str(observed)).quantize(Decimal('0.0001')) if observed is not None else None
        policy.coverage_rate_source = RateSource.OBSERVED if observed is not None else ''
        log('POLICY', policy.id, policy.policy_number,
            f"Police {policy.policy_number} : taux observé rétabli ({_pct(old)} -> {_pct(policy.coverage_rate)}).",
            {'from': _rate(old), 'to': _rate(policy.coverage_rate), 'source': 'OBSERVED'})
    elif data.get('coverage_rate') not in (None, ''):
        rate = _parse_rate(data['coverage_rate'], f"Police {policy.policy_number}")
        if rate != policy.coverage_rate or policy.coverage_rate_source != RateSource.MANUAL:
            old = policy.coverage_rate
            policy.coverage_rate, policy.coverage_rate_source = rate, RateSource.MANUAL
            log('POLICY', policy.id, policy.policy_number,
                f"Police {policy.policy_number} : taux de couverture saisi {_pct(rate)} (avant : {_pct(old)}).",
                {'from': _rate(old), 'to': _rate(rate), 'source': 'MANUAL'})

    # Taux des plans
    for item in data.get('plans') or []:
        plan = GuaranteePlan.objects.select_for_update().filter(policy=policy, pk=item.get('id')).first()
        if plan is None:
            raise SettingsError("Plan de garanties introuvable sur cette police.")
        if item.get('reset'):
            observed = _observed_of(plan, ClaimLine.objects.filter(claim__policy=policy, claim__membership__plan=plan))
            old = plan.coverage_rate
            plan.coverage_rate = Decimal(str(observed)).quantize(Decimal('0.0001')) if observed is not None else None
            plan.coverage_rate_source = RateSource.OBSERVED if observed is not None else ''
            plan.save(update_fields=['coverage_rate', 'coverage_rate_source'])
            log('PLAN', plan.id, plan.label, f"Plan « {plan.label} » ({policy.policy_number}) : taux observé rétabli "
                f"({_pct(old)} -> {_pct(plan.coverage_rate)}).", {'from': _rate(old), 'to': _rate(plan.coverage_rate)})
        elif item.get('coverage_rate') not in (None, ''):
            rate = _parse_rate(item['coverage_rate'], f"Plan « {plan.label} »")
            if rate != plan.coverage_rate or plan.coverage_rate_source != RateSource.MANUAL:
                old = plan.coverage_rate
                plan.coverage_rate, plan.coverage_rate_source = rate, RateSource.MANUAL
                plan.save(update_fields=['coverage_rate', 'coverage_rate_source'])
                log('PLAN', plan.id, plan.label, f"Plan « {plan.label} » ({policy.policy_number}) : taux saisi "
                    f"{_pct(rate)} (avant : {_pct(old)}).", {'from': _rate(old), 'to': _rate(rate)})

    # Souscripteur : existant du pays, ou nouveau (entreprise / particulier)
    sub = None
    if data.get('subscriber_id'):
        sub = Subscriber.objects.filter(country=country, pk=data['subscriber_id']).first()
        if sub is None:
            raise SettingsError("Souscripteur introuvable dans votre pays.")
    elif data.get('subscriber'):
        kind = (data['subscriber'].get('kind') or '').upper()
        name = clean_text(data['subscriber'].get('name'))
        if kind not in Subscriber.Kind.values:
            raise SettingsError("Type de souscripteur invalide : entreprise ou particulier.")
        if not name:
            raise SettingsError("Saisissez le nom du souscripteur.")
        insured = None
        if kind == Subscriber.Kind.INDIVIDUAL:
            # Particulier : relié à l'assuré principal de la police qui porte ce nom, s'il existe
            from importer.reconciliation.normalize import name_key
            insured = next((m.insured for m in InsuredEmployer.objects.filter(policy=policy, role='primary')
                            .select_related('insured') if m.insured.name_key == name_key(name)), None)
        sub, _ = Subscriber.objects.get_or_create(country=country, kind=kind, name_key=text_key(name),
                                                  defaults={'name': name, 'insured': insured})
    if sub is not None and sub.pk != policy.subscriber_id:
        old = policy.subscriber
        policy.subscriber = sub
        log('POLICY', policy.id, policy.policy_number,
            f"Police {policy.policy_number} : souscripteur « {sub.name} » ({sub.get_kind_display().lower()})"
            + (f" au lieu de « {old.name} »." if old else "."),
            {'from': old.id if old else None, 'to': sub.id})

    policy.save(update_fields=['coverage_rate', 'coverage_rate_source', 'subscriber'])
    if not changes:
        raise SettingsError("Aucune modification à enregistrer.")
    return {'detail': ' '.join(changes), 'policy': policy_detail(country, policy.id)}
