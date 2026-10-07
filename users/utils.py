import csv
import io
import random
import re
import string
import unicodedata

import pandas as pd
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.conf import settings

ACCEPTED_IMPORT_FORMATS = ".xlsx, .xls, .csv"

INVALID_EMAIL_MESSAGE = (
    "Adresse e-mail invalide : vérifiez sa saisie (les lettres accentuées, espaces "
    "et caractères spéciaux ne sont pas acceptés)."
)


# Lettres qui ne se décomposent pas en « lettre + accent » (sinon elles disparaîtraient)
_TRANSLITERATION = str.maketrans({
    'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ß': 'ss',
    'đ': 'd', 'Đ': 'D', 'ł': 'l', 'Ł': 'L', 'þ': 'th', 'Þ': 'TH', 'ð': 'd', 'Ð': 'D',
})


def ascii_slug(text):
    """
    « Agbéko » → « agbeko », « N'Guessan » → « nguessan », « Jean Marc » → « jean-marc »,
    « Œdipe » → « oedipe ». Accents retirés, minuscules, apostrophes supprimées, tout autre
    caractère remplacé par un tiret.
    """
    text = str(text or '').translate(_TRANSLITERATION)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r"['’`]", '', text.lower())
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def build_username(first_name, last_name, exists):
    """
    Identifiant « prenom.nom » sans accent ni espace. En cas de doublon, un nombre aléatoire
    entre 1 et 999 est ajouté (« prenom.nom482 »), tiré à nouveau tant que l'identifiant est pris.
    `exists(username)` indique si un identifiant est déjà pris.
    """
    base = f"{ascii_slug(first_name) or 'utilisateur'}.{ascii_slug(last_name) or 'compte'}"[:140]
    username = base
    while exists(username):
        username = f"{base}{random.randint(1, 999)}"
    return username


def validate_account_email(value):
    """
    Adresse e-mail d'un compte : ASCII uniquement (pas d'accent, ni dans la partie locale
    ni dans le domaine) et format valide. Renvoie l'adresse sans espaces autour.
    Lève ValidationError (message en français) sinon.
    """
    value = str(value or '').strip()
    if not value or not value.isascii():
        raise ValidationError(INVALID_EMAIL_MESSAGE)
    try:
        validate_email(value)
    except ValidationError:
        raise ValidationError(INVALID_EMAIL_MESSAGE)
    return value


def read_import_file(file):
    """
    Read an uploaded user import file (.xlsx, .xls or .csv) into a DataFrame.

    CSV files are decoded as UTF-8 (with or without BOM) and fall back to Windows-1252,
    the encoding of CSV files saved by a French Excel. The separator (';', ',' or tab)
    is detected automatically: French Excel uses ';'. Empty cells are read as NaN,
    like with Excel files, and column names are stripped of surrounding spaces.

    Raises:
        ValueError: unsupported extension or unreadable file.
    """
    name = (getattr(file, 'name', '') or '').lower()

    if name.endswith('.csv'):
        raw = file.read()
        for encoding in ('utf-8-sig', 'cp1252'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("encodage du fichier CSV non reconnu")
        if not text.strip():
            raise ValueError("le fichier CSV est vide")
        try:
            separator = csv.Sniffer().sniff(text.splitlines()[0], delimiters=';,\t').delimiter
        except csv.Error:
            separator = ','
        df = pd.read_csv(io.StringIO(text), sep=separator, dtype=str, skipinitialspace=True)
    elif name.endswith(('.xlsx', '.xls')):
        try:
            df = pd.read_excel(file)  # .xlsx via openpyxl, .xls via xlrd
        except Exception as e:
            raise ValueError("fichier Excel illisible ou corrompu") from e
    else:
        raise ValueError(f"format non pris en charge (formats acceptés : {ACCEPTED_IMPORT_FORMATS})")

    df.columns = [str(column).strip() for column in df.columns]
    return df

def generate_password(length=12):
    """
    Generate a random password consisting of letters and digits.

    Args:
        length (int): Length of the password. Default is 12.

    Returns:
        str: The generated password.
    """
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def send_user_email(to_email, subject, plain_text_content, html_content=None):
    """
    Send an email to a user.

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject.
        plain_text_content (str): Plain text version of the email content.
        html_content (str or None): Optional HTML content for the email.

    Raises:
        Exception: Raises exception if sending email fails.
    """
    send_mail(
        subject,
        plain_text_content,
        settings.EMAIL_HOST_USER,
        [to_email],
        fail_silently=False,
        html_message=html_content
    )
