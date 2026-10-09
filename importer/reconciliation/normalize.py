"""Normalisation des valeurs lues dans les fichiers (textes, noms, montants, dates)."""
import re
import unicodedata

import pandas as pd

# Valeurs qui signifient « vide » dans les exports (le récap met « - » partout où il n'y a rien)
EMPTY_MARKERS = {'', '-', '--', 'nan', 'none', 'null', 'nat', 'n/a'}

# Origine des numéros de série Excel (1 = 01/01/1900, avec le faux 29/02/1900 d'Excel)
EXCEL_EPOCH = '1899-12-30'


def strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


def clean_text(value):
    """Texte nettoyé (espaces, apostrophes typographiques) ou None si la valeur est vide."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).replace('’', "'").replace(' ', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return None if text.lower() in EMPTY_MARKERS else text


def text_key(value):
    """Clé de comparaison d'un libellé : majuscules, sans accents, espaces réduits.
    'Évacuation  Sanitaire' et 'EVACUATION SANITAIRE' donnent la même clé."""
    text = clean_text(value)
    if text is None:
        return ''
    text = strip_accents(text).replace('�', '')
    return re.sub(r'\s+', ' ', text).strip().upper()


def name_key(value):
    """Clé de comparaison d'un nom de personne : comme text_key, sans ponctuation et sans tenir compte
    de l'ordre des mots ('LOGO AMEVI MESSANH' = 'AMEVI MESSANH LOGO'). Un caractère mal encodé (�)
    est retiré : 'G�RARD' et 'GÉRARD' ne donnent pas la même clé, ils seront signalés, pas fusionnés."""
    words = re.sub(r"[^A-Z0-9 ]", ' ', text_key(value)).split()
    return ' '.join(sorted(words))


def header_key(value):
    """Clé d'un en-tête de colonne : minuscules, sans accents ni ponctuation ni espaces.
    'N°cheque/Autre_Moyent_de_payement' -> 'nchequeautremoyentdepayement'."""
    if value is None:
        return ''
    return re.sub(r'[^a-z0-9]', '', strip_accents(str(value)).lower())


def claim_key(series):
    """Numéros de sinistre comparables : la statistique les écrit en minuscules, le récap en majuscules."""
    return series.map(clean_text).map(lambda v: v.upper().replace(' ', '') if v else None)


def parse_amounts(series):
    """Montants numériques. Accepte 1234, '1 234', '1234,50', '1.234,50' ; '-' et vide -> NaN."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)

    def one(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = clean_text(value)
        if text is None:
            return float('nan')
        text = text.replace(' ', '').replace(' ', '')
        if ',' in text and '.' in text:
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '.')
        try:
            return float(text)
        except ValueError:
            return float('nan')

    return series.map(one).astype(float)


_TEXT_DATE_FORMATS = ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%y', '%d/%m/%y', '%d.%m.%Y')


def parse_dates(series):
    """Dates (sans heure). Accepte les vraies dates Excel, les numéros de série Excel (45394)
    et le texte jour-mois-année ('29-12-2023', '29/12/2023') ; '-' et vide -> NaT."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series).dt.normalize()

    def one(value):
        if value is None:
            return pd.NaT
        if isinstance(value, pd.Timestamp):
            return value.normalize()
        if hasattr(value, 'year') and hasattr(value, 'month'):
            return pd.Timestamp(value).normalize()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if pd.isna(value) or not 1 <= value <= 2958465:
                return pd.NaT
            return (pd.Timestamp(EXCEL_EPOCH) + pd.to_timedelta(float(value), unit='D')).normalize()
        text = clean_text(value)
        if text is None:
            return pd.NaT
        text = text.split(' ')[0] if re.match(r'^\d{4}-\d{2}-\d{2} ', text) else text
        if re.fullmatch(r'\d+(\.\d+)?', text):
            return one(float(text))
        for fmt in _TEXT_DATE_FORMATS:
            try:
                return pd.to_datetime(text, format=fmt)
            except (ValueError, TypeError):
                continue
        return pd.NaT

    return pd.to_datetime(series.map(one), errors='coerce')
