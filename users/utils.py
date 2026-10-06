import csv
import io
import random
import string

import pandas as pd
from django.core.mail import send_mail
from django.conf import settings

ACCEPTED_IMPORT_FORMATS = ".xlsx, .xls, .csv"


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
        df = pd.read_excel(file)
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
