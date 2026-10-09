"""
Écriture en base des sinistres importables d'un rapprochement (lot I3, décisions des 08-09/10/2026).

Une seule transaction : tout est écrit, ou rien. Tout est cloisonné par le pays de la session.
Les référentiels sont retrouvés par leur clé normalisée, chargés en mémoire puis complétés par lots
(bulk_create) : quelques dizaines de requêtes au lieu d'une par ligne.

Règles :
- sinistre déjà en base (même pays, même numéro) : ignoré s'il est identique, non importé et signalé s'il diffère ;
- familles : un principal au sein d'une police ; un assuré est retrouvé par son identifiant (Broker_SunuId), sinon
  par son nom normalisé (sans accents, casse ni ordre des mots) parmi les adhérents de la police ; les fautes
  d'orthographe ne sont jamais fusionnées, seulement signalées ;
- le nom retenu pour un principal est celui de sa ligne en statut A ; un principal sans consommation est créé
  d'après la colonne « Assuré principal » de ses ayants droit (« déduit ») ;
- actes : variantes ramenées à leur libellé par la table d'alias ; un nouvel acte est rattaché à la catégorie la
  plus fréquente de ses lignes ;
- souscripteur d'une police déduit des employeurs (un seul, ou un préfixe commun avant « / »), sinon à renseigner ;
- taux de couverture observé (rapport remboursé / facturé le plus fréquent), jamais à la place d'un taux saisi.
"""
import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from datetime import datetime, time

import pandas as pd
from django.db import transaction
from django.utils import timezone

from core.models import (
    Act, ActAlias, ActCategory, Claim, ClaimLine, ClaimStatus, Client, GuaranteePlan, Insured, InsuredEmployer,
    Invoice, Operator, Partner, Payment, Policy, RateSource, Subscriber,
)
from importer.reconciliation.engine import CANCELLED_STATUS, fmt_date
from importer.reconciliation.normalize import clean_text, name_key, ref_key, text_key

ROLES = {'A': 'primary', 'C': 'spouse', 'E': 'child'}
CENT = Decimal('0.01')
BATCH = 1000


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def as_date(value):
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date()


def as_datetime(value):
    """Date -> date et heure (minuit, fuseau du projet), pour les dates du sinistre lues par les tableaux de bord."""
    d = as_date(value)
    return None if d is None else timezone.make_aware(datetime.combine(d, time.min))


def local_date(value):
    return None if value is None else timezone.localtime(value).date()


@dataclass
class WriteResult:
    created: Counter = field(default_factory=Counter)
    skipped_identical: list = field(default_factory=list)     # n° de sinistres déjà en base, identiques
    rejected: list = field(default_factory=list)              # {'N° sinistre', 'Motif', 'Détail'}
    insured_notes: list = field(default_factory=list)         # {'Police', 'Assuré', 'Motif', 'Détail'}
    policy_notes: list = field(default_factory=list)          # {'Police', 'Plan', 'Souscripteur', 'Taux…'}
    claimed: Decimal = Decimal('0')
    reimbursed: Decimal = Decimal('0')

    def summary(self):
        return {
            'created': dict(self.created),
            'skipped_identical': len(self.skipped_identical),
            'rejected': len(self.rejected),
            'insured_notes': len(self.insured_notes),
            'claimed': float(self.claimed),
            'reimbursed': float(self.reimbursed),
        }


class ClaimWriter:
    def __init__(self, session, result):
        self.session = session
        self.country = session.country
        self.currency = session.currency or (self.country.currency_code or '')[:3]
        self.result = result
        self.out = WriteResult()

    # ------------------------------------------------------------------ préparation
    def _prepare(self):
        L = self.result.importable_lines().copy()
        L['policy_key'] = L['policy_number'].map(ref_key)
        L['employer_name'] = L['employer'].map(clean_text)
        L['employer_key'] = L['employer_name'].map(lambda v: text_key(v) if v else '')
        L['benef_name'] = L['beneficiary'].map(lambda v: (clean_text(v) or '').upper())
        L['benef_key'] = L['beneficiary'].map(name_key)
        L['princ_name'] = L['main_insured'].map(lambda v: (clean_text(v) or '').upper())
        L['princ_key'] = L['main_insured'].map(name_key)
        # Employeur égal à l'assuré principal : police individuelle (décision K)
        individual = L['employer_key'].eq('') | (L['employer_name'].map(name_key) == L['princ_key'])
        L.loc[individual, 'employer_key'] = ''
        L['partner_key'] = L['partner'].map(text_key)
        L['category_key'] = L['act_category'].map(text_key)
        L['cancelled'] = L['claim_status_key'].eq(CANCELLED_STATUS)
        L['card'] = L['member_id'].map(clean_text) if 'member_id' in L else None
        for col in ('plan', 'operator', 'payment_ref', 'invoice_number', 'guarantee_label', 'note', 'act_name'):
            if col not in L:
                L[col] = None

        # Données indispensables pour rattacher le sinistre
        required = {'benef_key': 'bénéficiaire', 'policy_key': 'numéro de police', 'partner_key': 'partenaire',
                    'category_key': "catégorie d'acte"}
        bad = {}
        for col, label in required.items():
            for cid in L.loc[L[col].eq(''), 'claim_id'].unique():
                bad.setdefault(cid, []).append(label)
        for cid, labels in bad.items():
            self.out.rejected.append({'N° sinistre': cid, 'Motif': 'Donnée absente',
                                      'Détail': f"{', '.join(labels)} absent(s) sur au moins une ligne."})
        return L[~L['claim_id'].isin(bad)]

    def _skip_existing(self, L):
        """Décision 8 : déjà en base -> ignoré si identique, signalé s'il diffère."""
        totals = L.groupby('claim_id').agg(c=('claimed_amount', 'sum'), r=('reimbursed_amount', 'sum'),
                                           n=('claim_id', 'size'), d=('settlement_date', 'max'))
        existing = Claim.objects.filter(country=self.country, number__in=list(totals.index)).values(
            'number', 'claimed_amount', 'reimbursed_amount', 'lines_count', 'settlement_date', 'import_session_id')
        drop = set()
        for row in existing:
            t = totals.loc[row['number']]
            same = (money(t.c) == money(row['claimed_amount']) and money(t.r) == money(row['reimbursed_amount'])
                    and int(t.n) == row['lines_count'] and as_date(t.d) == local_date(row['settlement_date']))
            drop.add(row['number'])
            if same:
                self.out.skipped_identical.append(row['number'])
            else:
                self.out.rejected.append({
                    'N° sinistre': row['number'], 'Motif': 'Déjà en base avec des valeurs différentes',
                    'Détail': (f"En base (import n° {row['import_session_id']}) : facturé {money(row['claimed_amount'])}, "
                               f"remboursé {money(row['reimbursed_amount'])}, {row['lines_count']} ligne(s), réglé le "
                               f"{fmt_date(local_date(row['settlement_date']))} ; fichier : facturé {money(t.c)}, remboursé "
                               f"{money(t.r)}, {int(t.n)} ligne(s), réglé le {fmt_date(t.d)}."),
                })
        return L[~L['claim_id'].isin(drop)]

    # ------------------------------------------------------------------ référentiels simples
    def _ensure(self, model, existing_qs, keyfn, wanted, build):
        """Retrouve les objets existants (clé -> objet), crée les manquants par lot. `wanted` : clé -> données."""
        found = {keyfn(o): o for o in existing_qs}
        missing = [build(k, v) for k, v in wanted.items() if k not in found]
        if missing:
            # PostgreSQL renvoie les identifiants des objets créés par lot
            model.objects.bulk_create(missing, batch_size=BATCH)
            self.out.created[model.__name__] += len(missing)
            found.update({keyfn(o): o for o in missing})
        return found

    def _first_labels(self, L, key_col, value_col):
        out = {}
        for k, v in zip(L[key_col], L[value_col]):
            if k and k not in out:
                out[k] = clean_text(v) or k
        return out

    def _referentials(self, L):
        country, session = self.country, self.session

        cats = self._first_labels(L, 'category_key', 'act_category')
        self.categories = self._ensure(ActCategory, ActCategory.objects.filter(label_key__in=list(cats)),
                                       lambda o: o.label_key, cats,
                                       lambda k, v: ActCategory(label=v, label_key=k))

        aliases = dict(ActAlias.objects.values_list('alias_key', 'act_label'))
        act_label = L['act_name'].map(lambda v: aliases.get(text_key(v), clean_text(v)) if clean_text(v) else None)
        L['act_key'] = act_label.map(lambda v: text_key(v) if v else '')
        main_cat = (L[L['act_key'] != ''].groupby('act_key')['category_key']
                    .agg(lambda s: Counter(s).most_common(1)[0][0]))
        acts = {k: (lbl, main_cat[k]) for k, lbl in zip(L['act_key'], act_label) if k}
        self.acts = self._ensure(Act, Act.objects.filter(label_key__in=list(acts)), lambda o: o.label_key, acts,
                                 lambda k, v: Act(label=v[0], label_key=k, category=self.categories[v[1]]))

        partners = {}
        addresses = L['partner_address'] if 'partner_address' in L else [None] * len(L)
        for k, name, addr in zip(L['partner_key'], L['partner'], addresses):
            if k not in partners:
                partners[k] = (clean_text(name), clean_text(addr))
        self.partners = self._ensure(
            Partner, Partner.objects.filter(country=country, name_key__in=list(partners)), lambda o: o.name_key,
            partners, lambda k, v: Partner(country=country, name=v[0], name_key=k, address=v[1], import_session=session))

        L['operator_key'] = L['operator'].map(text_key)
        ops = self._first_labels(L, 'operator_key', 'operator')
        self.operators = self._ensure(
            Operator, Operator.objects.filter(country=country, name_key__in=list(ops)), lambda o: o.name_key, ops,
            lambda k, v: Operator(country=country, name=v.upper(), name_key=k))

        emps = self._first_labels(L, 'employer_key', 'employer_name')
        self.employers = self._ensure(
            Client, Client.objects.filter(country=country, name_key__in=list(emps)), lambda o: o.name_key, emps,
            lambda k, v: Client(country=country, name=v, name_key=k, import_session=session))

        pols = self._first_labels(L, 'policy_key', 'policy_number')
        self.policies = self._ensure(
            Policy, Policy.objects.filter(country=country, number_key__in=list(pols)), lambda o: o.number_key, pols,
            lambda k, v: Policy(country=country, policy_number=v.upper(), number_key=k, import_session=session))
        links = {(self.policies[p].pk, self.employers[e].pk) for p, e in zip(L['policy_key'], L['employer_key']) if e}
        Through = Policy.employers.through
        Through.objects.bulk_create([Through(policy_id=p, client_id=c) for p, c in links], ignore_conflicts=True)

        L['plan_key'] = L['plan'].map(text_key)
        plans = {}
        for p, k, v in zip(L['policy_key'], L['plan_key'], L['plan']):
            if k and (p, k) not in plans:
                plans[(p, k)] = clean_text(v)
        policy_ids = [o.pk for o in self.policies.values()]
        self.plans = self._ensure(
            GuaranteePlan, GuaranteePlan.objects.filter(policy_id__in=policy_ids).select_related('policy'),
            lambda o: (o.policy.number_key, o.label_key), plans,
            lambda k, v: GuaranteePlan(policy=self.policies[k[0]], label=v, label_key=k[1], import_session=session))

        partner_ids = [o.pk for o in self.partners.values()]
        L['invoice_key'] = L['invoice_number'].map(ref_key)
        invs = {}
        for pk, k, v in zip(L['partner_key'], L['invoice_key'], L['invoice_number']):
            if k and (pk, k) not in invs:
                invs[(pk, k)] = clean_text(v if not isinstance(v, float) else ref_key(v))
        self.invoices = self._ensure(
            Invoice, Invoice.objects.filter(country=country, partner_id__in=partner_ids).select_related('partner'),
            lambda o: (o.partner.name_key, o.number_key), invs,
            lambda k, v: Invoice(country=country, partner=self.partners[k[0]], invoice_number=v, number_key=k[1],
                                 import_session=session))

        L['payment_key'] = L['payment_ref'].map(ref_key)
        pays = {}
        for pk, k, v, d in zip(L['partner_key'], L['payment_key'], L['payment_ref'], L['settlement_date']):
            if k:
                prev = pays.get((pk, k))
                pays[(pk, k)] = (clean_text(v) if not isinstance(v, float) else ref_key(v),
                                 max(d, prev[1]) if prev else d)
        self.payments = self._ensure(
            Payment, Payment.objects.filter(country=country, partner_id__in=partner_ids).select_related('partner'),
            lambda o: (o.partner.name_key, o.reference_key), pays,
            lambda k, v: Payment(country=country, partner=self.partners[k[0]], reference=v[0], reference_key=k[1],
                                 payment_date=as_date(v[1]), import_session=session))

    # ------------------------------------------------------------------ familles d'assurés
    def _note(self, policy, insured, motif, detail=''):
        self.out.insured_notes.append({'Police': policy, 'Assuré': insured, 'Motif': motif, 'Détail': detail})

    def _families(self, L):
        country, session = self.country, self.session
        policy_objs = list(self.policies.values())

        # Assurés déjà connus, par police : clé de nom (et autres écritures) -> assuré ; et par identifiant
        known = defaultdict(dict)
        for m in InsuredEmployer.objects.filter(policy__in=policy_objs).select_related('insured', 'policy'):
            ins = m.insured
            for key in [ins.name_key] + [name_key(n) for n in ins.other_names]:
                known[m.policy.number_key].setdefault(key, ins)
        cards = {c for c in L['card'].dropna().unique()} if L['card'] is not None else set()
        by_card = {i.card_number: i for i in Insured.objects.filter(country=country, card_number__in=cards)}

        new_insureds, touched = [], {}
        self.person = {}        # (police, clé du bénéficiaire) -> Insured
        roles = {}              # (police, clé) -> rôle
        principal_of = {}       # (police, clé) -> (police, clé du principal)

        for pkey, P in L.groupby('policy_key', sort=False):
            policy_label = self.policies[pkey].policy_number
            people = {}
            for row in P.itertuples(index=False):
                p = people.setdefault(row.benef_key, {'names': Counter(), 'status': Counter(), 'princ': Counter(),
                                                      'princ_names': Counter(), 'card': None, 'a_names': Counter()})
                p['names'][row.benef_name] += 1
                p['status'][row.insured_status or '?'] += 1
                p['princ'][row.princ_key] += 1
                p['princ_names'][row.princ_name] += 1
                if row.insured_status == 'A':
                    p['a_names'][row.benef_name] += 1
                if row.card and not p['card']:
                    p['card'] = row.card

            # Rôle : le statut le plus fréquent ; plusieurs statuts -> signalé
            for key, p in people.items():
                st = [s for s, _ in p['status'].most_common() if s in ROLES]
                role = ROLES[st[0]] if st else ('primary' if p['princ'].most_common(1)[0][0] == key else 'other')
                if len([s for s in p['status'] if s in ROLES]) > 1:
                    self._note(policy_label, p['names'].most_common(1)[0][0], 'Plusieurs statuts pour une même personne',
                               f"{dict(p['status'])} : rôle retenu « {dict(InsuredEmployer.ROLE_CHOICES)[role]} ».")
                roles[(pkey, key)] = role

            # Principaux de la police : statut A ; la colonne « Assuré principal » de leurs lignes est une autre écriture
            alias = {}
            for key, p in people.items():
                if roles[(pkey, key)] != 'primary':
                    continue
                alias[key] = key
                for pk_, n in p['princ'].items():
                    if pk_ and pk_ != key:
                        alias.setdefault(pk_, key)
                        variant = [nm for nm in p['princ_names'] if name_key(nm) == pk_][0]
                        self._note(policy_label, p['a_names'].most_common(1)[0][0] if p['a_names'] else variant,
                                   "Nom du principal écrit autrement", f"Colonne « Assuré principal » : « {variant} ».")

            # Ayants droit : principal retrouvé, sinon principal déduit
            deduced = {}
            for key, p in people.items():
                if roles[(pkey, key)] == 'primary':
                    continue
                pk_ = p['princ'].most_common(1)[0][0]
                target = alias.get(pk_)
                if target is None and pk_ in known[pkey]:
                    # Principal déjà en base (import précédent), sans ligne dans ce fichier
                    target = pk_
                    self.person.setdefault((pkey, target), known[pkey][pk_])
                    roles.setdefault((pkey, target), 'primary')
                if target is None:
                    target = pk_
                    if pk_ not in deduced:
                        name = [nm for nm in p['princ_names'] if name_key(nm) == pk_][0]
                        deduced[pk_] = name
                        close = difflib.get_close_matches(pk_, [k for k in alias if alias[k] == k], n=1, cutoff=0.85)
                        if close:
                            near = people[close[0]]['a_names'].most_common(1)
                            self._note(policy_label, name, 'Principal sans consommation, nom proche d\'un autre principal',
                                       f"Créé séparément de « {near[0][0] if near else close[0]} » : à confirmer.")
                principal_of[(pkey, key)] = (pkey, target)
                if len(p['princ']) > 1:
                    self._note(policy_label, p['names'].most_common(1)[0][0], 'Plusieurs principaux pour un ayant droit',
                               ', '.join(f"« {n} »" for n in p['princ_names']))

            # Objets Insured : identifiant, sinon nom parmi les adhérents de la police, sinon création
            def resolve(key, name, card, is_deduced, others):
                ins = by_card.get(card) if card else None
                if ins is None:
                    ins = known[pkey].get(key)
                if ins is None:
                    ins = Insured(country=country, name=name, name_key=key, card_number=card or None,
                                  is_deduced=is_deduced, other_names=sorted(others), import_session=session)
                    new_insureds.append(ins)
                    if card:
                        by_card[card] = ins
                    known[pkey][key] = ins
                    return ins
                changed = False
                if is_deduced is False and ins.is_deduced:
                    ins.is_deduced, changed = False, True
                extra = [n for n in others if n != ins.name and n not in ins.other_names]
                if extra:
                    ins.other_names = sorted(set(ins.other_names) | set(extra))
                    changed = True
                if card and not ins.card_number:
                    if card in by_card and by_card[card] is not ins:
                        self._note(policy_label, ins.name, 'Identifiant déjà attribué à un autre assuré', card)
                    else:
                        ins.card_number, changed = card, True
                        by_card[card] = ins
                if changed and ins.pk:
                    touched[ins.pk] = ins
                return ins

            for key, p in people.items():
                is_primary = roles[(pkey, key)] == 'primary'
                # Nom retenu : celui de la ligne en statut A pour un principal (décision C), sauf caractère mal
                # encodé (« BA�NAMAY�M ») quand une autre écriture identique aux accents près existe
                name = (p['a_names'] or p['names']).most_common(1)[0][0]
                if '�' in name:
                    pattern = re.compile('^' + re.escape(name).replace('�', '.') + '$')
                    clean = [n for n in list(p['names']) + list(p['princ_names']) if '�' not in n and pattern.match(n)]
                    if clean:
                        name = clean[0]
                # Autres écritures : celles du bénéficiaire et, pour un principal, celles de la colonne
                # « Assuré principal » de ses propres lignes (ordre des mots ou orthographe différents)
                others = set(p['names']) | (set(p['princ_names']) if is_primary else set())
                others.discard(name)
                self.person[(pkey, key)] = resolve(key, name, p['card'], False, others)
            for key, name in deduced.items():
                if (pkey, key) not in self.person:
                    self.person[(pkey, key)] = resolve(key, name, None, True, set())
                    roles[(pkey, key)] = 'primary'
                    self.out.created['principaux déduits'] += 1

        Insured.objects.bulk_create(new_insureds, batch_size=BATCH)
        self.out.created['Insured'] += len(new_insureds)
        if touched:
            Insured.objects.bulk_update(list(touched.values()), ['is_deduced', 'other_names', 'card_number'], batch_size=BATCH)

        # Adhésions (assuré, police, employeur) : rôle, principal, plan, première / dernière consommation
        stats = (L.groupby(['policy_key', 'benef_key', 'employer_key'])
                 .agg(start=('settlement_date', 'min'), end=('settlement_date', 'max'),
                      plan=('plan_key', lambda s: Counter(x for x in s if x).most_common(1)[0][0] if any(s) else '')))
        wanted = {}
        for (pkey, key, ekey), row in stats.iterrows():
            principal = principal_of.get((pkey, key))
            wanted[(pkey, key, ekey)] = dict(
                role=roles[(pkey, key)], principal=self.person[principal] if principal else None,
                plan=self.plans.get((pkey, row.plan)) if row.plan else None,
                start=as_date(row.start), end=as_date(row.end))
            # Principal déduit : adhésion chez l'employeur de son ayant droit
            if principal and (principal[0], principal[1], ekey) not in stats.index:
                wanted.setdefault((principal[0], principal[1], ekey), dict(role='primary', principal=None, plan=None,
                                                                           start=None, end=None))

        existing = {(m.policy.number_key, m.insured_id, m.employer_id): m for m in
                    InsuredEmployer.objects.filter(policy__in=policy_objs).select_related('policy')}
        self.membership, create, update = {}, [], []
        for (pkey, key, ekey), w in wanted.items():
            ins, emp = self.person[(pkey, key)], self.employers.get(ekey) if ekey else None
            m = existing.get((pkey, ins.pk, emp.pk if emp else None))
            if m is None:
                m = InsuredEmployer(insured=ins, policy=self.policies[pkey], employer=emp, role=w['role'],
                                    primary_insured_ref=w['principal'], plan=w['plan'], start_date=w['start'],
                                    end_date=w['end'], import_session=session)
                create.append(m)
            else:
                if w['start'] and (not m.start_date or w['start'] < m.start_date):
                    m.start_date = w['start']
                if w['end'] and (not m.end_date or w['end'] > m.end_date):
                    m.end_date = w['end']
                if w['plan'] and not m.plan_id:
                    m.plan = w['plan']
                update.append(m)
            self.membership[(pkey, key, ekey)] = m
        InsuredEmployer.objects.bulk_create(create, batch_size=BATCH)
        self.out.created['InsuredEmployer'] += len(create)
        if update:
            InsuredEmployer.objects.bulk_update(update, ['start_date', 'end_date', 'plan'], batch_size=BATCH)

    # ------------------------------------------------------------------ souscripteurs et taux
    def _policies(self, L):
        country, session = self.country, self.session
        for pkey, P in L.groupby('policy_key', sort=False):
            policy = self.policies[pkey]
            note = {'Police': policy.policy_number, 'Plan': '', 'Souscripteur': '', 'Taux observé': None,
                    'Taux enregistré': None, 'Remarque': ''}
            if policy.subscriber_id is None:
                names = sorted({e.name for e in policy.employers.all()})
                kind, name, insured = None, None, None
                if not names:
                    principals = [self.person[(pkey, k)] for k in P['benef_key'].unique()
                                  if self.membership.get((pkey, k, '')) and self.membership[(pkey, k, '')].role == 'primary']
                    if len(principals) == 1:
                        kind, name, insured = Subscriber.Kind.INDIVIDUAL, principals[0].name, principals[0]
                elif len(names) == 1:
                    kind, name = Subscriber.Kind.COMPANY, names[0]
                else:
                    prefixes = {n.split('/')[0].strip() for n in names}
                    if len(prefixes) == 1:
                        kind, name = Subscriber.Kind.COMPANY, prefixes.pop()
                if kind:
                    sub, created = Subscriber.objects.get_or_create(
                        country=country, kind=kind, name_key=text_key(name),
                        defaults={'name': name, 'insured': insured, 'import_session': session})
                    self.out.created['Subscriber'] += int(created)
                    policy.subscriber = sub
                    note['Souscripteur'] = f"{sub.name} ({sub.get_kind_display()}, déduit)"
                else:
                    note['Remarque'] = 'Souscripteur à renseigner (plusieurs employeurs sans nom commun).'
            else:
                note['Souscripteur'] = policy.subscriber.name

            rate = self._observed_rate(P)
            note['Taux observé'] = float(rate) if rate is not None else None
            if rate is not None and policy.coverage_rate_source != RateSource.MANUAL:
                policy.coverage_rate, policy.coverage_rate_source = rate, RateSource.OBSERVED
            note['Taux enregistré'] = float(policy.coverage_rate) if policy.coverage_rate is not None else None
            if policy.coverage_rate_source == RateSource.MANUAL and rate is not None and rate != policy.coverage_rate:
                note['Remarque'] = (note['Remarque'] + ' Taux saisi différent du taux observé.').strip()
            policy.save(update_fields=['subscriber', 'coverage_rate', 'coverage_rate_source'])
            self.out.policy_notes.append(note)

            for plan_key, PP in P[P['plan_key'] != ''].groupby('plan_key'):
                plan = self.plans[(pkey, plan_key)]
                rate = self._observed_rate(PP)
                if rate is not None and plan.coverage_rate_source != RateSource.MANUAL:
                    plan.coverage_rate, plan.coverage_rate_source = rate, RateSource.OBSERVED
                    plan.save(update_fields=['coverage_rate', 'coverage_rate_source'])
                self.out.policy_notes.append({
                    'Police': policy.policy_number, 'Plan': plan.label, 'Souscripteur': '',
                    'Taux observé': float(rate) if rate is not None else None,
                    'Taux enregistré': float(plan.coverage_rate) if plan.coverage_rate is not None else None,
                    'Remarque': ''})

    @staticmethod
    def _observed_rate(lines):
        ok = lines[(lines['claimed_amount'] > 0) & (lines['reimbursed_amount'] > 0)]
        if ok.empty:
            return None
        ratios = (ok['reimbursed_amount'] / ok['claimed_amount']).round(2)
        return Decimal(str(Counter(ratios).most_common(1)[0][0])).quantize(Decimal('0.0001'))

    # ------------------------------------------------------------------ sinistres et lignes
    def _claims(self, L):
        session, country, cur = self.session, self.country, self.currency
        claims, lines_by_claim = [], []
        for cid, C in L.groupby('claim_id', sort=False):
            first = C.iloc[0]
            pkey, key, ekey = first.policy_key, first.benef_key, first.employer_key
            claimed, reimbursed = money(C['claimed_amount'].sum()), money(C['reimbursed_amount'].sum())
            cancelled = bool(C['cancelled'].any()) and abs(claimed) < 5 and abs(reimbursed) < 5
            ops = [o for o in C['operator_key'] if o]
            pays = [p for p in C['payment_key'] if p]
            notes = [n for n in C['note'].map(clean_text) if n]
            incident = C['incident_date'].dropna()
            claim = Claim(
                country=country, number=cid, status=ClaimStatus.CANCELLED if cancelled else ClaimStatus.SETTLED,
                claim_date=as_datetime(incident.min()) if len(incident) else None,
                settlement_date=as_datetime(C['settlement_date'].max()),
                insured=self.person[(pkey, key)], policy=self.policies[pkey],
                employer=self.employers.get(ekey) if ekey else None,
                membership=self.membership[(pkey, key, ekey)], partner=self.partners[first.partner_key],
                operator=self.operators.get(ops[-1]) if ops else None,
                payment=self.payments.get((first.partner_key, pays[0])) if pays else None,
                currency=cur, claimed_amount=float(claimed), reimbursed_amount=float(reimbursed), lines_count=len(C),
                note=notes[0] if notes else '', import_session=session,
            )
            claims.append(claim)
            lines_by_claim.append(C)
            self.out.claimed += claimed
            self.out.reimbursed += reimbursed

        Claim.objects.bulk_create(claims, batch_size=BATCH)
        self.out.created['Claim'] += len(claims)

        lines = []
        for claim, C in zip(claims, lines_by_claim):
            for n, row in enumerate(C.itertuples(index=False), start=1):
                lines.append(ClaimLine(
                    claim=claim, line_number=n, category=self.categories[row.category_key],
                    act=self.acts.get(row.act_key) if row.act_key else None,
                    guarantee_label=(clean_text(row.guarantee_label) or '')[:500],
                    invoice=self.invoices.get((row.partner_key, row.invoice_key)) if row.invoice_key else None,
                    status=ClaimStatus.CANCELLED if row.cancelled else ClaimStatus.SETTLED,
                    settlement_date=as_date(row.settlement_date), currency=cur,
                    claimed_amount=money(row.claimed_amount), reimbursed_amount=money(row.reimbursed_amount),
                    operator=self.operators.get(row.operator_key) if row.operator_key else None,
                ))
        ClaimLine.objects.bulk_create(lines, batch_size=BATCH)
        self.out.created['ClaimLine'] += len(lines)

    # ------------------------------------------------------------------
    def write(self):
        with transaction.atomic():
            L = self._prepare()
            L = self._skip_existing(L)
            if not L.empty:
                self._referentials(L)
                self._families(L)
                self._policies(L)
                self._claims(L)
        return self.out


def write_claims(session, result):
    return ClaimWriter(session, result).write()
