"""
Primes des employeurs et ratio S/P (lot I4, décisions du 10/10/2026).

Primes
- Absentes des fichiers de sinistres : saisies, ou importées d'un fichier .xlsx / .xls / .csv (colonnes : employeur,
  prime, période couverte), par l'admin territorial ou le chef de département technique du pays.
- Une prime par employeur et par période couverte, sans chevauchement ; l'historique est conservé (une entreprise
  peut passer de 2 M à 3 M au contrat suivant). Chaque création, modification ou suppression est tracée
  (ReferenceChange, objet PREMIUM).

Ratio S/P sur une période analysée [début, fin]
- S = consommation (montant remboursé des sinistres, date de règlement) ; P = la prime **entière** en vigueur, même
  si la période analysée n'en couvre qu'une partie (un trimestre, un semestre…).
- Un ratio par période de prime : S sur la partie de la période analysée couverte par cette prime / montant de la prime.
- Périodes de prime consécutives de **même montant** : en plus, un ratio d'ensemble = somme de leurs S / ce montant
  (la prime n'a pas changé). Si les montants diffèrent, pas de ratio d'ensemble pour cet employeur.
- Plusieurs employeurs (pays, police…) : S couverts additionnés / primes additionnées, chaque suite de périodes de
  même montant comptant une fois.
"""
import difflib
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction
from django.db.models import Sum

from core.models import Claim, Client, Premium, ReferenceChange
from importer.reconciliation.normalize import clean_text, parse_amounts, parse_dates, text_key


class PremiumError(Exception):
    """Saisie refusée : message renvoyé tel quel."""


def _d(value):
    """date, datetime ou chaîne AAAA-MM-JJ -> date."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _fmt(d):
    return d.strftime('%d/%m/%Y')


def _money(value):
    return round(float(value or 0), 2)


def _user_name(user):
    return f'{user.first_name} {user.last_name}'.strip() or user.username


def premium_json(p):
    return {'id': p.id, 'client_id': p.client_id, 'amount': _money(p.amount), 'currency': p.currency,
            'start_date': p.start_date.isoformat(), 'end_date': p.end_date.isoformat(), 'source': p.source,
            'source_label': p.get_source_display(), 'file_name': p.file_name, 'note': p.note,
            'created_by': p.created_by_name, 'updated_at': p.updated_at.isoformat()}


# ------------------------------------------------------------------ ratio S/P
def _groups(premiums):
    """Suites de périodes consécutives de même montant (une prime inchangée d'un contrat à l'autre)."""
    groups = []
    for p in sorted(premiums, key=lambda x: x.start_date):
        if groups and groups[-1][-1].amount == p.amount:
            groups[-1].append(p)
        else:
            groups.append([p])
    return groups


def _consumption(claims, client_id, start, end):
    total = claims.filter(employer_id=client_id, settlement_date__date__gte=start,
                          settlement_date__date__lte=end).aggregate(s=Sum('reimbursed_amount'))['s']
    return float(total or 0)


def client_sp(client, start, end, claims=None):
    """Détail du S/P d'un employeur sur [start, end] : un ratio par période de prime, et un ratio d'ensemble pour
    chaque suite de périodes de même montant. `claims` : sinistres à prendre en compte (par défaut, ceux du pays)."""
    start, end = _d(start), _d(end)
    claims = claims if claims is not None else Claim.objects.filter(country_id=client.country_id)
    premiums = list(Premium.objects.filter(client=client, start_date__lte=end, end_date__gte=start))
    periods, covered = [], 0.0
    by_id = {}
    for p in sorted(premiums, key=lambda x: x.start_date):
        a, b = max(start, p.start_date), min(end, p.end_date)
        s = _consumption(claims, client.id, a, b)
        covered += s
        row = {'premium_id': p.id, 'premium_start': p.start_date.isoformat(), 'premium_end': p.end_date.isoformat(),
               'start': a.isoformat(), 'end': b.isoformat(), 'premium': _money(p.amount), 'consumption': _money(s),
               'ratio': round(s / float(p.amount), 4), 'partial': a > p.start_date or b < p.end_date}
        periods.append(row)
        by_id[p.id] = row
    groups = []
    for g in _groups(premiums):
        s = sum(by_id[p.id]['consumption'] for p in g)
        groups.append({'start': by_id[g[0].id]['start'], 'end': by_id[g[-1].id]['end'], 'periods': len(g),
                       'premium': _money(g[0].amount), 'consumption': _money(s), 'ratio': round(s / float(g[0].amount), 4)})
    total = _consumption(claims, client.id, start, end)
    same_amount = len(groups) == 1
    return {
        'client_id': client.id, 'client': client.name, 'start': start.isoformat(), 'end': end.isoformat(),
        'periods': periods,
        'groups': groups,
        # Un seul ratio d'ensemble quand la prime n'a pas changé sur toute la période analysée
        'overall': groups[0] if same_amount else None,
        'consumption_total': _money(total),
        'consumption_uncovered': _money(total - covered),   # sinistres hors de toute période de prime
    }


def sp_summary(client_ids, start, end, claims=None):
    """S/P d'un ensemble d'employeurs : S couverts additionnés / primes additionnées (une suite de périodes de même
    montant compte une fois). Renvoie {'premium', 'consumption', 'ratio', 'clients_with_premium'}."""
    start, end = _d(start), _d(end)
    claims = claims if claims is not None else Claim.objects.all()
    premiums = defaultdict(list)
    for p in Premium.objects.filter(client_id__in=list(client_ids), start_date__lte=end, end_date__gte=start):
        premiums[p.client_id].append(p)
    total_p = total_s = 0.0
    for client_id, plist in premiums.items():
        for g in _groups(plist):
            total_p += float(g[0].amount)
            for p in g:
                total_s += _consumption(claims, client_id, max(start, p.start_date), min(end, p.end_date))
    return {'premium': _money(total_p), 'consumption': _money(total_s),
            'ratio': round(total_s / total_p, 4) if total_p else None, 'clients_with_premium': len(premiums)}


def current_summary(client_ids, claims, today=None):
    """Indicateurs « actuels » (sans période choisie) : primes en vigueur aujourd'hui, et S depuis le début de chacune
    de ces primes jusqu'à aujourd'hui. Renvoie {'premium', 'consumption', 'ratio'}."""
    today = today or date.today()
    total_p = total_s = 0.0
    for p in Premium.objects.filter(client_id__in=list(client_ids), start_date__lte=today, end_date__gte=today):
        total_p += float(p.amount)
        total_s += _consumption(claims, p.client_id, p.start_date, today)
    return {'premium': _money(total_p), 'consumption': _money(total_s),
            'ratio': round(total_s / total_p, 4) if total_p else None}


def premium_total(client_ids, start, end):
    """Total des primes en vigueur sur [start, end] (entières ; une suite de même montant compte une fois)."""
    return sp_summary(client_ids, start, end, claims=Claim.objects.none())['premium']


def premium_series(client_ids, periods, date_end):
    """Série des primes en vigueur par tranche de temps (`periods` : débuts de tranches, comme generate_periods) :
    pour chaque tranche, somme des primes entières qui la couvrent (même règle que premium_total)."""
    out = []
    for i, start in enumerate(periods):
        stop = periods[i + 1] - timedelta(days=1) if i + 1 < len(periods) else date_end
        out.append({'period': start, 'value': premium_total(client_ids, _d(start), _d(stop))})
    return out


def sp_series(client_ids, periods, date_end, claims):
    """Série du ratio S/P par tranche de temps : consommation de la tranche / primes entières en vigueur sur la tranche
    (None si aucune prime). `claims` : sinistres déjà filtrés (pays, employeur, police…)."""
    out = []
    ids = list(client_ids)
    for i, start in enumerate(periods):
        stop = periods[i + 1] - timedelta(days=1) if i + 1 < len(periods) else date_end
        a, b = _d(start), _d(stop)
        premium = premium_total(ids, a, b)
        s = claims.filter(employer_id__in=ids, settlement_date__date__gte=a, settlement_date__date__lte=b) \
            .aggregate(s=Sum('reimbursed_amount'))['s'] or 0
        out.append({'period': start, 'value': round(float(s) / premium, 4) if premium else None})
    return out


# ------------------------------------------------------------------ saisie
def _check_overlap(client, start, end, exclude_id=None):
    qs = Premium.objects.filter(client=client, start_date__lte=end, end_date__gte=start)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    other = qs.first()
    if other:
        raise PremiumError(f"{client.name} : la période chevauche une prime existante "
                           f"(du {_fmt(other.start_date)} au {_fmt(other.end_date)}).")


def _parse_amount(value):
    try:
        amount = Decimal(str(value).replace(' ', '').replace(' ', '').replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise PremiumError(f"Montant de prime invalide : « {value} ».")
    if amount <= 0:
        raise PremiumError("Le montant de la prime doit être positif.")
    return amount.quantize(Decimal('0.01'))


def _parse_period(start, end):
    try:
        a, b = _d(start), _d(end)
    except ValueError:
        raise PremiumError("Dates de période invalides (format AAAA-MM-JJ).")
    if not a or not b:
        raise PremiumError("Indiquez le début et la fin de la période couverte.")
    if b < a:
        raise PremiumError("La fin de la période est antérieure à son début.")
    return a, b


def _log(country, user, client, summary, details):
    ReferenceChange.objects.create(country=country, object_type='PREMIUM', object_id=client.id, label=client.name,
                                   summary=summary, details=details, user=user, user_name=_user_name(user))


@transaction.atomic
def create_premium(country, user, data):
    client = Client.objects.filter(country=country, pk=data.get('client_id')).first()
    if client is None:
        raise PremiumError("Employeur introuvable dans votre pays.")
    amount = _parse_amount(data.get('amount'))
    start, end = _parse_period(data.get('start_date'), data.get('end_date'))
    _check_overlap(client, start, end)
    p = Premium.objects.create(country=country, client=client, amount=amount, currency=country.currency_code or '',
                               start_date=start, end_date=end, source=Premium.Source.MANUAL,
                               note=(clean_text(data.get('note')) or '')[:500], created_by=user,
                               created_by_name=_user_name(user))
    _log(country, user, client, f"{client.name} : prime de {amount:,.0f} {p.currency} du {_fmt(start)} au {_fmt(end)} "
         "saisie.".replace(',', ' '), {'premium': p.id, 'amount': float(amount)})
    return p


@transaction.atomic
def update_premium(country, user, premium_id, data):
    p = Premium.objects.select_for_update().filter(country=country, pk=premium_id).select_related('client').first()
    if p is None:
        raise PremiumError("Prime introuvable dans votre pays.")
    old = (p.amount, p.start_date, p.end_date)
    amount = _parse_amount(data['amount']) if data.get('amount') not in (None, '') else p.amount
    start, end = _parse_period(data.get('start_date') or p.start_date, data.get('end_date') or p.end_date)
    _check_overlap(p.client, start, end, exclude_id=p.id)
    if (amount, start, end) == old and data.get('note') is None:
        raise PremiumError("Aucune modification à enregistrer.")
    p.amount, p.start_date, p.end_date = amount, start, end
    if data.get('note') is not None:
        p.note = (clean_text(data.get('note')) or '')[:500]
    p.save()
    _log(country, user, p.client,
         f"{p.client.name} : prime du {_fmt(old[1])} au {_fmt(old[2])} ({old[0]:,.0f}) modifiée -> {amount:,.0f}, "
         f"du {_fmt(start)} au {_fmt(end)}.".replace(',', ' '),
         {'premium': p.id, 'from': [float(old[0]), old[1].isoformat(), old[2].isoformat()],
          'to': [float(amount), start.isoformat(), end.isoformat()]})
    return p


@transaction.atomic
def delete_premium(country, user, premium_id):
    p = Premium.objects.filter(country=country, pk=premium_id).select_related('client').first()
    if p is None:
        raise PremiumError("Prime introuvable dans votre pays.")
    _log(country, user, p.client, f"{p.client.name} : prime de {p.amount:,.0f} du {_fmt(p.start_date)} au "
         f"{_fmt(p.end_date)} supprimée.".replace(',', ' '),
         {'premium': p.id, 'amount': float(p.amount), 'start': p.start_date.isoformat(), 'end': p.end_date.isoformat()})
    p.delete()


def employers_with_premiums(country, search=''):
    """Employeurs du pays et leurs primes (historique), ceux sans prime compris."""
    clients = Client.objects.filter(country=country).prefetch_related('policies')
    if search:
        clients = clients.filter(name_key__icontains=text_key(search))
    premiums = defaultdict(list)
    for p in Premium.objects.filter(country=country).order_by('-start_date'):
        premiums[p.client_id].append(premium_json(p))
    today = date.today()
    rows = []
    for c in clients.order_by('name'):
        plist = premiums.get(c.id, [])
        current = next((p for p in plist if p['start_date'] <= today.isoformat() <= p['end_date']), None)
        rows.append({'id': c.id, 'name': c.name, 'policies': sorted(p.policy_number for p in c.policies.all()),
                     'premiums': plist, 'current': current, 'last': plist[0] if plist else None})
    return rows


def history(country, client_id):
    return [{'summary': h.summary, 'user': h.user_name, 'date': h.created_at.isoformat()}
            for h in ReferenceChange.objects.filter(country=country, object_type='PREMIUM', object_id=client_id)[:100]]


# ------------------------------------------------------------------ import de fichier
HEADERS = {
    'employer': ('EMPLOYEUR', 'NOM EMPLOYEUR', 'NOM DE L EMPLOYEUR', 'NOM DE LEMPLOYEUR', 'CLIENT', 'NOM CLIENT',
                 'ENTREPRISE', 'SOUSCRIPTEUR'),
    'amount': ('PRIME', 'MONTANT', 'MONTANT PRIME', 'MONTANT DE LA PRIME', 'PRIME ANNUELLE'),
    'start': ('DEBUT', 'DATE DEBUT', 'DATE DE DEBUT', 'DEBUT PERIODE', 'DEBUT DE PERIODE', 'DEBUT DE LA PERIODE',
              'DU', 'PERIODE DU', 'DATE EFFET', 'DATE D EFFET'),
    'end': ('FIN', 'DATE FIN', 'DATE DE FIN', 'FIN PERIODE', 'FIN DE PERIODE', 'FIN DE LA PERIODE', 'AU',
            'PERIODE AU', 'DATE ECHEANCE', 'DATE D ECHEANCE'),
    'period': ('PERIODE', 'PERIODE COUVERTE', 'PERIODE DE COUVERTURE', 'ANNEE', 'EXERCICE'),
}
TEMPLATE_COLUMNS = ['Employeur', 'Prime', 'Début période', 'Fin période']


def _header_key(name):
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9 ]', ' ', text_key(name))).strip()


def _map_columns(columns):
    found = {}
    for col in columns:
        key = _header_key(col)
        for field, names in HEADERS.items():
            if key in names and field not in found:
                found[field] = col
    return found


def _split_period(value):
    """« 2025 » -> année entière ; « 01/01/2025 - 31/12/2025 » ou « 01/01/2025 au 31/12/2025 » -> deux dates."""
    text = clean_text(value)
    if text is None:
        return None, None
    if re.fullmatch(r'\d{4}(\.0)?', text):
        y = int(float(text))
        return date(y, 1, 1), date(y, 12, 31)
    m = re.match(r'^\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s*(?:-|–|au|à|a)\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s*$', text,
                 re.IGNORECASE)
    if not m:
        return None, None
    a, b = parse_dates(pd.Series([m.group(1).replace('.', '/'), m.group(2).replace('.', '/')]))
    return (a.date() if not pd.isna(a) else None), (b.date() if not pd.isna(b) else None)


def import_premiums(country, user, df, file_name, dry_run=False):
    """Importe les primes d'un tableau (DataFrame lu par users.utils.read_import_file). Import partiel : les lignes
    valides sont enregistrées (une transaction), les autres renvoyées avec leur motif. `dry_run` : contrôle seul."""
    cols = _map_columns(df.columns)
    missing = [label for field, label in (('employer', 'Employeur'), ('amount', 'Prime')) if field not in cols]
    if 'period' not in cols and not ('start' in cols and 'end' in cols):
        missing.append('Période couverte (« Période » ou « Début période » et « Fin période »)')
    if missing:
        raise PremiumError("Colonnes manquantes : " + ', '.join(missing) + ". Colonnes attendues : "
                           + ', '.join(TEMPLATE_COLUMNS) + ".")
    df = df.dropna(how='all')
    if df.empty:
        raise PremiumError("Le fichier ne contient aucune ligne.")

    amounts = parse_amounts(df[cols['amount']])
    if 'start' in cols and 'end' in cols:
        starts, ends = parse_dates(df[cols['start']]), parse_dates(df[cols['end']])
        periods = [(None if pd.isna(a) else a.date(), None if pd.isna(b) else b.date()) for a, b in zip(starts, ends)]
    else:
        periods = [_split_period(v) for v in df[cols['period']]]

    clients = {c.name_key: c for c in Client.objects.filter(country=country)}
    names = list(clients)
    existing = defaultdict(list)
    for p in Premium.objects.filter(country=country):
        existing[p.client_id].append(p)

    rows, planned = [], defaultdict(list)
    for i, (raw_name, amount, (start, end)) in enumerate(zip(df[cols['employer']], amounts, periods)):
        line = int(df.index[i]) + 2
        name = clean_text(raw_name)
        row = {'line': line, 'employer': name or '', 'amount': None if pd.isna(amount) else _money(amount),
               'start_date': start.isoformat() if start else None, 'end_date': end.isoformat() if end else None,
               'status': 'REJECTED', 'status_label': 'Rejetée', 'reason': ''}
        rows.append(row)
        if not name:
            row['reason'] = "Employeur absent."
            continue
        client = clients.get(text_key(name))
        if client is None:
            close = difflib.get_close_matches(text_key(name), names, n=1, cutoff=0.8)
            row['reason'] = "Employeur introuvable dans votre pays" + (
                f" (vouliez-vous dire « {clients[close[0]].name} » ?)." if close else ".")
            continue
        row['employer'] = client.name
        if pd.isna(amount) or amount <= 0:
            row['reason'] = "Montant de prime absent ou invalide."
            continue
        if not start or not end:
            row['reason'] = "Période couverte absente ou illisible."
            continue
        if end < start:
            row['reason'] = "La fin de la période est antérieure à son début."
            continue
        dup = next((o for o in planned[client.id] if o['start'] <= end and o['end'] >= start), None)
        if dup:
            row['reason'] = f"Chevauche la ligne {dup['line']} du fichier pour le même employeur."
            continue
        value = Decimal(str(amount)).quantize(Decimal('0.01'))
        same = next((p for p in existing[client.id] if p.start_date == start and p.end_date == end), None)
        overlap = next((p for p in existing[client.id] if p is not same and p.start_date <= end and p.end_date >= start), None)
        if overlap:
            row['reason'] = (f"Chevauche la prime enregistrée du {_fmt(overlap.start_date)} au {_fmt(overlap.end_date)} "
                             "(à modifier ou supprimer d'abord).")
            continue
        if same and same.amount == value:
            row.update(status='SAME', status_label='Déjà enregistrée', reason='Prime identique déjà enregistrée.')
            continue
        row.update(status='UPDATE' if same else 'NEW', status_label='Mise à jour' if same else 'Nouvelle')
        if same:
            row['reason'] = f"Remplace {same.amount:,.0f}.".replace(',', ' ')
        planned[client.id].append({'line': line, 'start': start, 'end': end, 'client': client, 'amount': value,
                                   'same': same, 'row': row})

    counts = defaultdict(int)
    for r in rows:
        counts[r['status']] += 1
    result = {'file': file_name, 'dry_run': dry_run, 'rows': rows,
              'counts': {'new': counts['NEW'], 'update': counts['UPDATE'], 'same': counts['SAME'],
                         'rejected': counts['REJECTED'], 'total': len(rows)}}
    if dry_run:
        return result

    with transaction.atomic():
        for items in planned.values():
            for it in items:
                client, same = it['client'], it['same']
                if same:
                    old = same.amount
                    same.amount, same.source, same.file_name = it['amount'], Premium.Source.IMPORT, file_name[:255]
                    same.save()
                    _log(country, user, client, f"{client.name} : prime du {_fmt(same.start_date)} au "
                         f"{_fmt(same.end_date)} mise à jour par import ({old:,.0f} -> {it['amount']:,.0f}).".replace(',', ' '),
                         {'premium': same.id, 'file': file_name})
                else:
                    p = Premium.objects.create(country=country, client=client, amount=it['amount'],
                                               currency=country.currency_code or '', start_date=it['start'],
                                               end_date=it['end'], source=Premium.Source.IMPORT,
                                               file_name=file_name[:255], created_by=user,
                                               created_by_name=_user_name(user))
                    _log(country, user, client, f"{client.name} : prime de {it['amount']:,.0f} du {_fmt(it['start'])} "
                         f"au {_fmt(it['end'])} importée.".replace(',', ' '), {'premium': p.id, 'file': file_name})
    return result


def template_bytes():
    """Modèle Excel du fichier d'import des primes."""
    import io
    buf = io.BytesIO()
    pd.DataFrame([['NOM DE L\'EMPLOYEUR', 2000000, '01/01/2025', '31/12/2025']], columns=TEMPLATE_COLUMNS) \
        .to_excel(buf, index=False, engine='xlsxwriter')
    return buf.getvalue()
