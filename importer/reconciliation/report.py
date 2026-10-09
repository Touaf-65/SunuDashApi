"""Rapport Excel du rapprochement (lot I2), écrit avec XlsxWriter : des dizaines de milliers de lignes
en quelques secondes (openpyxl, en Python pur, demandait plus d'une minute)."""
import datetime as dt
import io

import numpy as np
import pandas as pd
import xlsxwriter

from .engine import IMPORTABLE, NON_CONFORME, CONFORME, ANNULE, fmt_date
from .sources import ORIGIN_COLUMNS

DATE_FORMAT = 'dd/mm/yyyy'
AMOUNT_FORMAT = '#,##0'
SECTION = '§'   # ligne d'intertitre dans la synthèse
TITLE = '#'     # titre de la synthèse

CLAIM_COLUMNS = [
    ('N° sinistre', None), ('Catégorie', 'categorie'), ('Observation', 'observation'),
    ('Bénéficiaire', 'beneficiaire'), ('Assuré principal', 'assure_principal'), ('Statut assuré', 'statut_assure'),
    ('Police', 'police'), ('Employeur', 'employeur'), ('Partenaire', 'partenaire'),
    ('Date de règlement (statistique)', 'date_reglement_stat'), ('Date de règlement (récap)', 'date_reglement_recap'),
    ('Facturé (statistique)', 'facture_stat'), ('Facturé (récap)', 'facture_recap'), ('Écart facturé', 'ecart_facture'),
    ('Remboursé (statistique)', 'rembourse_stat'), ('Remboursé (récap)', 'rembourse_recap'),
    ('Écart remboursé', 'ecart_rembourse'), ("Lignes d'actes", 'lignes'),
]
AMOUNT_HEADERS = {'Facturé (statistique)', 'Facturé (récap)', 'Écart facturé', 'Remboursé (statistique)',
                  'Remboursé (récap)', 'Écart remboursé', 'Montant facturé', 'Montant remboursé',
                  'totalmttreclame', 'totalmttrembourse'}


def _plain(v):
    """Valeur écrivable : None pour le vide, types Python pour numpy."""
    if v is None:
        return None
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and v != v:
        return None
    if v is pd.NaT:
        return None
    return v


class _Writer:
    def __init__(self):
        self.buffer = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buffer, {
            'in_memory': True,
            # Le contenu des fichiers est écrit tel quel : jamais interprété comme formule, lien ou nombre
            'strings_to_formulas': False, 'strings_to_urls': False, 'strings_to_numbers': False,
            'nan_inf_to_errors': True,
        })
        self.header = self.wb.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1F4E78',
                                          'text_wrap': True, 'valign': 'vcenter'})
        self.date = self.wb.add_format({'num_format': DATE_FORMAT})
        self.amount = self.wb.add_format({'num_format': AMOUNT_FORMAT})
        self.amount_left = self.wb.add_format({'num_format': AMOUNT_FORMAT, 'align': 'left'})
        self.title = self.wb.add_format({'bold': True, 'font_size': 14})
        self.section = self.wb.add_format({'bold': True, 'font_size': 12, 'font_color': '#1F4E78'})

    def table(self, title, frame, widths=None, date_columns=(), amount_columns=()):
        """Une feuille = un tableau avec en-tête, filtre et volets figés."""
        ws = self.wb.add_worksheet(title[:31])
        headers = [str(c) for c in frame.columns]
        for i, header in enumerate(headers):
            width = (widths or {}).get(header) or min(max(len(header) + 2, 12), 45)
            ws.set_column(i, i, width)
            ws.write_string(0, i, header, self.header)
        ws.freeze_panes(1, 0)
        if headers:
            ws.autofilter(0, 0, max(len(frame), 1), len(headers) - 1)

        kinds = []
        for h in headers:
            kinds.append('date' if h in date_columns else
                         'amount' if (h in amount_columns or h in AMOUNT_HEADERS) else None)
        values = frame.astype(object).to_numpy()
        for r, row in enumerate(values, start=1):
            for c, v in enumerate(row):
                v = _plain(v)
                if v is None:
                    continue
                kind = kinds[c]
                if isinstance(v, dt.datetime):
                    ws.write_datetime(r, c, v, self.date)
                elif isinstance(v, bool):
                    ws.write_string(r, c, 'Oui' if v else 'Non')
                elif isinstance(v, (int, float)):
                    ws.write_number(r, c, v, self.amount if kind == 'amount' else None)
                else:
                    ws.write_string(r, c, str(v))
        return ws

    def summary(self, title, rows):
        """rows : (libellé, valeur) ; (SECTION, texte) = intertitre ; (TITLE, texte) = titre."""
        ws = self.wb.add_worksheet(title)
        ws.set_column(0, 0, 58)
        ws.set_column(1, 1, 60)
        r = 0
        for label, value in rows:
            if label == TITLE:
                ws.write_string(r, 0, value, self.title)
            elif label == SECTION:
                r += 1
                ws.write_string(r, 0, value, self.section)
            else:
                ws.write_string(r, 0, label)
                value = _plain(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    ws.write_number(r, 1, value, self.amount_left)
                elif value is not None:
                    ws.write_string(r, 1, str(value))
            r += 1
        ws.activate()

    def save(self):
        self.wb.close()
        return self.buffer.getvalue()


def _claims_frame(claims):
    frame = pd.DataFrame({
        header: (claims.index if source is None else claims[source]) for header, source in CLAIM_COLUMNS
    })
    order = {cat: i for i, cat in enumerate(NON_CONFORME + IMPORTABLE)}
    frame['_ordre'] = frame['Catégorie'].map(order)
    return frame.sort_values(['_ordre', 'N° sinistre']).drop(columns='_ordre')


def _stat_lines(res, index, extra=None):
    """Lignes d'origine de la statistique, dates de règlement et de sinistre lisibles (le fichier
    contient parfois des numéros de série Excel)."""
    raw = res.stat.raw.loc[index].copy()
    for canonical in ('settlement_date', 'incident_date'):
        col = res.stat.mapping.get(canonical)
        if col:
            raw[col] = res.stat.data.loc[index, canonical]
    if extra is not None:
        for name, values in reversed(list(extra.items())):
            raw.insert(0, name, values)
    return raw


def _recap_lines(res, index, extra=None):
    raw = res.recap.raw.loc[index].copy()
    if extra is not None:
        for name, values in reversed(list(extra.items())):
            raw.insert(0, name, values)
    return raw


def _date_cols(res):
    return {res.stat.mapping.get('settlement_date'), res.stat.mapping.get('incident_date'),
            'Date de règlement (statistique)', 'Date de règlement (récap)'} - {None}


def build_report(res, meta=None, write=None):
    """Classeur Excel (bytes). `meta` : pays, auteur, session, date, dry_run… ; `write` : résultat de
    l'écriture en base (writer_service.WriteResult), qui ajoute sa synthèse et ses feuilles."""
    meta = meta or {}
    s = res.summary
    claims = res.claims
    w = _Writer()
    dates = _date_cols(res)
    by_cat = s['claims']['by_category']

    stat_label = ', '.join(res.stat.files) + (f" — feuille « {meta['sheet']} »" if meta.get('sheet') else '')
    rows = [
        (TITLE, 'Rapport de rapprochement — import des sinistres'),
        ('Session d\'import', meta.get('session_id')),
        ('Pays', meta.get('country')),
        ('Analyse lancée par', meta.get('user')),
        ('Date de l\'analyse', meta.get('date') or dt.datetime.now().strftime('%d/%m/%Y %H:%M')),
    ]
    if meta.get('currency'):
        rows.append(('Devise des montants', meta['currency']))
    if write is None and meta.get('dry_run', True):
        rows.append(('Écriture en base', "Aucune : rapprochement seul, en attente de validation."))
    if write is not None:
        c = write.created
        rows += [
            (SECTION, 'Écriture en base'),
            ('Sinistres importés', c['Claim']),
            ("Lignes d'actes importées", c['ClaimLine']),
            ('Montant facturé importé', float(write.claimed)),
            ('Montant remboursé importé', float(write.reimbursed)),
            ('Déjà en base à l\'identique (ignorés)', len(write.skipped_identical)),
            ("Rejetés à l'écriture (voir « Rejets à l'écriture »)", len(write.rejected)),
            ('Assurés créés (dont principaux déduits)', f"{c['Insured']} (dont {c['principaux déduits']})"),
            ('Adhésions créées', c['InsuredEmployer']),
            ('Employeurs / polices / plans créés', f"{c['Client']} / {c['Policy']} / {c['GuaranteePlan']}"),
            ('Souscripteurs créés', c['Subscriber']),
            ('Partenaires / opérateurs créés', f"{c['Partner']} / {c['Operator']}"),
            ('Catégories / actes créés', f"{c['ActCategory']} / {c['Act']}"),
            ('Factures / paiements créés', f"{c['Invoice']} / {c['Payment']}"),
            ('Points à vérifier sur les assurés', len(write.insured_notes)),
        ]
    rows += [
        (SECTION, 'Fichiers'),
        ('Fichier statistique', stat_label),
        ('Fichiers récap', f"{s['recap']['files']} fichier(s)"),
        (SECTION, 'Périodes (date de règlement)'),
        ('Statistique', f"du {fmt_date(res.stat_range[0])} au {fmt_date(res.stat_range[1])}"),
        ('Récaps (sinistres payés)', f"du {fmt_date(res.recap_range[0])} au {fmt_date(res.recap_range[1])}"),
        ('Période commune', f"du {fmt_date(res.period[0])} au {fmt_date(res.period[1])}"),
        ('Tolérance sur les écarts', f"écart inférieur à {res.tolerance:g} sur le facturé et sur le remboursé"),
        (SECTION, 'Sinistres de la statistique sur la période commune'),
        ('Total', s['claims']['total']),
        (f"{CONFORME} (importables)", by_cat[CONFORME]),
        (f"{ANNULE} : réglés puis annulés, total nul (importables)", by_cat[ANNULE]),
    ]
    rows += [(f"Non conformes — {cat}", by_cat[cat]) for cat in NON_CONFORME]
    rows += [
        ('Total non conformes (non importés)', s['claims']['non_conform']),
        (SECTION, 'Importables'),
        ('Sinistres', s['importable']['claims']),
        ("Lignes d'actes", s['importable']['lines']),
        ('Montant facturé', s['importable']['claimed']),
        ('Montant remboursé', s['importable']['reimbursed']),
        (SECTION, 'Hors période commune (non importés)'),
        ('Lignes de la statistique', s['out_of_period']['lines']),
        ('Sinistres concernés', s['out_of_period']['claims']),
        (SECTION, 'Récaps'),
        ('Lignes lues (après retrait des lignes identiques)', s['recap']['rows']),
        ('Lignes identiques retirées (pages qui se chevauchent)', s['recap']['duplicate_rows_removed']),
        ('Sinistres non payés (sans date de règlement), exclus', s['recap']['unpaid']),
        ('Sinistres en double avec des valeurs différentes', s['recap']['divergent_claims']),
        ('Sinistres seulement dans le récap (information)', s['claims']['recap_only']),
        (SECTION, 'Anomalies de lecture'),
        ('Lignes illisibles de la statistique', s['stat']['unreadable_lines']),
        ('Lignes illisibles des récaps', s['recap']['unreadable_rows']),
        (SECTION, 'Feuilles de ce rapport'),
        ('Non conformes', 'un sinistre par ligne, avec le motif et les montants des deux côtés'),
        ('Lignes stat non conformes / Lignes récap non conformes', "les lignes d'origine de ces sinistres"),
        ('Annulés', 'sinistres réglés puis annulés (contre-passation), importables'),
        ('Hors période', 'lignes de la statistique en dehors de la période commune'),
        ('Récaps non payés', 'lignes du récap sans date de règlement'),
        ('Doublons récap', 'sinistres présents plusieurs fois dans le récap avec des valeurs différentes'),
        ('Seulement dans le récap', 'sinistres payés sur la période, absents de la statistique'),
        ('Conformes', 'sinistres importables'),
        ('Anomalies de lecture', 'lignes illisibles des deux côtés'),
    ]
    if write is not None:
        rows += [
            ("Rejets à l'écriture", 'sinistres importables non écrits (déjà en base avec d\'autres valeurs, donnée absente)'),
            ('Assurés à vérifier', "variantes de noms, principaux déduits proches d'un autre, rôles incohérents"),
            ('Polices et taux', 'souscripteur déduit ou à renseigner, taux de couverture observés'),
            ('Déjà en base (identiques)', 'sinistres ignorés car déjà importés à l\'identique'),
        ]
    w.summary('Synthèse', rows)

    widths = {'Observation': 70, 'N° sinistre': 32, 'Bénéficiaire': 30, 'Assuré principal': 30,
              'Employeur': 30, 'Partenaire': 30}
    non_conform = claims[claims['categorie'].isin(NON_CONFORME)]
    w.table('Non conformes', _claims_frame(non_conform), widths, dates)

    nc_ids = set(non_conform.index)
    cat_of = claims['categorie']
    stat_nc = res.stat.data.index[res.stat.data['claim_id'].isin(nc_ids)]
    w.table('Lignes stat non conformes',
            _stat_lines(res, stat_nc, {'Catégorie': res.stat.data.loc[stat_nc, 'claim_id'].map(cat_of)}),
            date_columns=dates)
    recap_nc = res.recap.data.index[res.recap.data['claim_id'].isin(nc_ids)]
    w.table('Lignes récap non conformes',
            _recap_lines(res, recap_nc, {'Catégorie': res.recap.data.loc[recap_nc, 'claim_id'].map(cat_of)}))

    w.table('Annulés', _claims_frame(claims[claims['categorie'] == ANNULE]), widths, dates)
    w.table('Hors période', _stat_lines(res, res.out_of_period_index), date_columns=dates)
    w.table('Récaps non payés', _recap_lines(res, res.unpaid_index))
    w.table('Doublons récap', _recap_lines(res, res.divergent_index))
    w.table('Seulement dans le récap',
            _recap_lines(res, res.recap_only.index, {'Observation': res.recap_only['observation']}),
            widths={'Observation': 50})
    w.table('Conformes', _claims_frame(claims[claims['categorie'] == CONFORME]), widths, dates)

    anomalies = pd.concat([
        _stat_lines(res, res.stat.anomalies.index, {'Côté': 'Statistique', 'Motif': res.stat.anomalies['motif']}),
        _recap_lines(res, res.recap.anomalies.index, {'Côté': 'Récap', 'Motif': res.recap.anomalies['motif']}),
    ], ignore_index=True)
    lead = ['Côté', 'Motif'] + ORIGIN_COLUMNS
    anomalies = anomalies[lead + [c for c in anomalies.columns if c not in lead]]
    w.table('Anomalies de lecture', anomalies, {'Motif': 45}, date_columns=dates)

    if write is not None:
        w.table("Rejets à l'écriture", pd.DataFrame(write.rejected, columns=['N° sinistre', 'Motif', 'Détail']),
                {'N° sinistre': 32, 'Motif': 40, 'Détail': 110})
        w.table('Assurés à vérifier', pd.DataFrame(write.insured_notes, columns=['Police', 'Assuré', 'Motif', 'Détail']),
                {'Police': 24, 'Assuré': 36, 'Motif': 50, 'Détail': 70})
        w.table('Polices et taux', pd.DataFrame(write.policy_notes, columns=['Police', 'Plan', 'Souscripteur',
                                                                            'Taux observé', 'Taux enregistré', 'Remarque']),
                {'Police': 24, 'Plan': 40, 'Souscripteur': 45, 'Remarque': 60})
        w.table('Déjà en base (identiques)', pd.DataFrame({'N° sinistre': write.skipped_identical}),
                {'N° sinistre': 32})
    return w.save()
