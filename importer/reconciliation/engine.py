"""
Rapprochement statistique / récap (lot I2). Aucune écriture en base.

Règles décidées avec l'utilisateur (08-09/10/2026) :
- période commune calculée sur la date de règlement ; pas de période commune -> arrêt, avec les deux plages ;
- montants de la statistique additionnés par sinistre (une ligne par acte), comparés aux totaux du récap ;
  conforme si l'écart est inférieur à la tolérance (5 par défaut) sur le facturé ET sur le remboursé ;
- sinistre seulement dans la statistique -> non conforme (absent du récap) ;
  seulement dans le récap -> information, sans blocage ;
- lignes de la statistique hors période commune -> non importées, signalées ;
- récap sans date de règlement (non payé) -> exclu du rapprochement, listé ;
- sinistre présent deux fois dans le récap avec des valeurs différentes -> non conforme ;
- contre-passation (lignes « Annulée » négatives) : comparaison sur le total net ; un sinistre au total
  nul absent du récap est « annulé » : importable, sans être compté non conforme ;
- les sinistres conformes (et annulés) sont importables, les autres sont listés dans le rapport.
"""
from dataclasses import dataclass, field

import pandas as pd

TOLERANCE = 5

CONFORME = 'Conforme'
ANNULE = 'Annulé'
ECART = 'Écart de montant'
ABSENT_RECAP = 'Absent du récap'
DOUBLON_RECAP = 'Doublon divergent dans le récap'
ILLISIBLE = 'Lignes illisibles'

IMPORTABLE = (CONFORME, ANNULE)
NON_CONFORME = (ECART, ABSENT_RECAP, DOUBLON_RECAP, ILLISIBLE)

CANCELLED_STATUS = 'ANNULEE'


class NoCommonPeriod(Exception):
    def __init__(self, stat_range, recap_range):
        self.stat_range, self.recap_range = stat_range, recap_range
        super().__init__(
            "Aucune période commune entre les deux fichiers : statistique du "
            f"{fmt_date(stat_range[0])} au {fmt_date(stat_range[1])}, récap du "
            f"{fmt_date(recap_range[0])} au {fmt_date(recap_range[1])}. Rien n'a été importé."
        )


class NoUsableData(Exception):
    pass


def fmt_date(value):
    return '' if value is None or pd.isna(value) else pd.Timestamp(value).strftime('%d/%m/%Y')


def fmt_amount(value):
    return f"{value:,.0f}".replace(',', ' ')


@dataclass
class Result:
    stat: object                          # sources.Prepared
    recap: object                         # sources.Prepared
    tolerance: float
    stat_range: tuple
    recap_range: tuple
    period: tuple
    claims: pd.DataFrame                  # un sinistre de la statistique par ligne, avec sa catégorie
    recap_only: pd.DataFrame              # lignes du récap (payées, période commune) absentes de la statistique
    out_of_period_index: pd.Index         # lignes de la statistique hors période
    unpaid_index: pd.Index                # lignes du récap non payées
    divergent_index: pd.Index             # lignes du récap en double avec des valeurs différentes
    summary: dict = field(default_factory=dict)

    @property
    def importable_claim_ids(self):
        return list(self.claims.index[self.claims['categorie'].isin(IMPORTABLE)])


def _range(dates):
    dates = dates.dropna()
    if dates.empty:
        return (None, None)
    return (dates.min(), dates.max())


def _observation(row, tol):
    parts = []
    dc, dr = row['ecart_facture'], row['ecart_rembourse']
    if abs(dc) >= tol:
        parts.append(f"Facturé : statistique {fmt_amount(row['facture_stat'])}, récap {fmt_amount(row['facture_recap'])} "
                     f"(écart {fmt_amount(dc)}).")
    if abs(dr) >= tol:
        parts.append(f"Remboursé : statistique {fmt_amount(row['rembourse_stat'])}, récap {fmt_amount(row['rembourse_recap'])} "
                     f"(écart {fmt_amount(dr)}).")
    recap_c = row['facture_recap']
    if recap_c and abs(row['facture_stat'] - 2 * recap_c) < tol:
        parts.append("La statistique vaut le double du récap : lignes d'actes saisies deux fois ?")
    if row['lignes_identiques'] > 0:
        parts.append(f"{int(row['lignes_identiques'])} ligne(s) strictement identique(s) dans la statistique.")
    return ' '.join(parts)


def reconcile(stat, recap, tolerance=TOLERANCE):
    """`stat` et `recap` : sources.Prepared. Lève NoCommonPeriod ou NoUsableData."""
    s, r = stat.data, recap.data

    s_bad = s.index.isin(stat.anomalies.index)
    r_bad = r.index.isin(recap.anomalies.index)
    s_ok = s[~s_bad]
    r_paid = r[~r_bad & ~r['unpaid']]

    stat_range, recap_range = _range(s_ok['settlement_date']), _range(r_paid['settlement_date'])
    if stat_range[0] is None:
        raise NoUsableData("Le fichier statistique ne contient aucune ligne exploitable (date de règlement, montants).")
    if recap_range[0] is None:
        raise NoUsableData("Les récaps ne contiennent aucun sinistre payé exploitable.")

    start, end = max(stat_range[0], recap_range[0]), min(stat_range[1], recap_range[1])
    if start > end:
        raise NoCommonPeriod(stat_range, recap_range)

    in_period = s_ok['settlement_date'].between(start, end)
    lines = s_ok[in_period]
    out_of_period_index = s_ok.index[~in_period]

    # Récap : doublons divergents (même sinistre, valeurs différentes, après retrait des lignes identiques)
    dup_mask = r_paid['claim_id'].duplicated(keep=False)
    divergent_ids = set(r_paid.loc[dup_mask, 'claim_id'])
    r_single = r_paid[~dup_mask]
    r_period_rows = r_single[r_single['settlement_date'].between(start, end)]
    r_period = r_period_rows.set_index('claim_id')

    # Sinistres de la statistique (lignes de la période)
    raw_cols = list(stat.mapping.values())
    dup_lines = stat.raw.loc[lines.index].duplicated(subset=raw_cols, keep='first')
    work = lines.assign(
        annulee=lines['claim_status_key'].eq(CANCELLED_STATUS),
        identique=dup_lines.values,
    )
    first = lambda col: (col, 'first')
    agg = {
        'facture_stat': ('claimed_amount', 'sum'),
        'rembourse_stat': ('reimbursed_amount', 'sum'),
        'lignes': ('claim_id', 'size'),
        'lignes_annulees': ('annulee', 'sum'),
        'lignes_identiques': ('identique', 'sum'),
        'date_reglement_stat': ('settlement_date', 'max'),
        'beneficiaire': first('beneficiary'),
        'assure_principal': first('main_insured'),
        'statut_assure': first('insured_status'),
        'police': first('policy_number'),
        'employeur': first('employer'),
        'partenaire': first('partner'),
    }
    claims = work.groupby('claim_id').agg(**agg)

    rp = r_period.reindex(claims.index)
    claims['dans_recap'] = claims.index.isin(r_period.index)
    claims['facture_recap'] = rp['claimed_amount']
    claims['rembourse_recap'] = rp['reimbursed_amount']
    claims['date_reglement_recap'] = rp['settlement_date']
    # Écart vide (NaN) quand le sinistre n'est pas dans le récap
    claims['ecart_facture'] = claims['facture_stat'] - claims['facture_recap']
    claims['ecart_rembourse'] = claims['rembourse_stat'] - claims['rembourse_recap']

    unreadable_ids = set(s.loc[s_bad, 'claim_id'].dropna())
    unpaid_ids = set(r.loc[r['unpaid'], 'claim_id'].dropna())
    recap_other_dates = r_single.set_index('claim_id')['settlement_date']

    def classify(row):
        cid = row.name
        if cid in unreadable_ids:
            return ILLISIBLE, "Certaines lignes de ce sinistre sont illisibles (voir la feuille « Anomalies de lecture »)."
        if cid in divergent_ids:
            return DOUBLON_RECAP, "Présent plusieurs fois dans le récap avec des valeurs différentes."
        if row['dans_recap']:
            ok = abs(row['ecart_facture']) < tolerance and abs(row['ecart_rembourse']) < tolerance
            return (CONFORME, '') if ok else (ECART, _observation(row, tolerance))
        cancelled_to_zero = (row['lignes_annulees'] > 0 and abs(row['facture_stat']) < tolerance
                             and abs(row['rembourse_stat']) < tolerance)
        if cancelled_to_zero:
            return ANNULE, "Sinistre réglé puis annulé (total net nul), absent du récap."
        if cid in unpaid_ids:
            return ABSENT_RECAP, "Présent dans le récap mais sans date de règlement (non payé)."
        if cid in recap_other_dates.index:
            return ABSENT_RECAP, (f"Présent dans le récap avec une date de règlement hors période "
                                  f"({fmt_date(recap_other_dates.loc[cid])}).")
        return ABSENT_RECAP, "Absent des récaps."

    classified = claims.apply(classify, axis=1, result_type='expand') if len(claims) else pd.DataFrame(columns=[0, 1])
    claims['categorie'] = classified[0] if len(claims) else pd.Series(dtype=str)
    claims['observation'] = classified[1] if len(claims) else pd.Series(dtype=str)

    # Récap seul : sinistres payés de la période absents de la statistique (information)
    recap_only = r_period_rows[~r_period_rows['claim_id'].isin(claims.index)].copy()
    stat_all_ids = set(s_ok['claim_id'])
    recap_only['observation'] = [
        "Présent dans la statistique avec une date de règlement hors période." if cid in stat_all_ids else ''
        for cid in recap_only['claim_id']
    ]

    result = Result(
        stat=stat, recap=recap, tolerance=tolerance,
        stat_range=stat_range, recap_range=recap_range, period=(start, end),
        claims=claims, recap_only=recap_only,
        out_of_period_index=out_of_period_index,
        unpaid_index=r.index[r['unpaid'] & ~r_bad],
        divergent_index=r_paid.index[dup_mask],
    )
    result.summary = build_summary(result)
    return result


def build_summary(res):
    claims = res.claims
    counts = {cat: int((claims['categorie'] == cat).sum()) for cat in IMPORTABLE + NON_CONFORME}
    importable = claims[claims['categorie'].isin(IMPORTABLE)]
    out_lines = res.stat.data.loc[res.out_of_period_index]
    iso = lambda d: None if d is None or pd.isna(d) else pd.Timestamp(d).date().isoformat()
    return {
        'tolerance': res.tolerance,
        'stat': {
            'files': res.stat.files,
            'lines': int(len(res.stat.data)),
            'claims': int(res.stat.data['claim_id'].nunique()),
            'unreadable_lines': int(len(res.stat.anomalies)),
            'start': iso(res.stat_range[0]), 'end': iso(res.stat_range[1]),
        },
        'recap': {
            'files': len(res.recap.files),
            'rows': int(len(res.recap.data)),
            'duplicate_rows_removed': int(res.recap.duplicate_rows_removed),
            'unpaid': int(len(res.unpaid_index)),
            'divergent_claims': int(res.recap.data.loc[res.divergent_index, 'claim_id'].nunique()),
            'unreadable_rows': int(len(res.recap.anomalies)),
            'start': iso(res.recap_range[0]), 'end': iso(res.recap_range[1]),
        },
        'period': {'start': iso(res.period[0]), 'end': iso(res.period[1])},
        'claims': {
            'total': int(len(claims)),
            'by_category': counts,
            'non_conform': int(sum(counts[c] for c in NON_CONFORME)),
            'recap_only': int(len(res.recap_only)),
        },
        'out_of_period': {'lines': int(len(out_lines)), 'claims': int(out_lines['claim_id'].nunique())},
        'importable': {
            'claims': int(len(importable)),
            'lines': int(importable['lignes'].sum()),
            'claimed': float(importable['facture_stat'].sum()),
            'reimbursed': float(importable['rembourse_stat'].sum()),
        },
    }
