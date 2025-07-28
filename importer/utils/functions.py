import unicodedata
import re
import pandas as pd
import os
from datetime import datetime
from rest_framework.response import Response
from .constants import COLUMN_SYNONYMS

def open_excel_csv(file):
    """
    Opens an Excel or CSV file and loads it into a DataFrame.

    Args:
        file: The file to open, which can be an Excel file (.xlsx, .xls) or a CSV file (.csv).

    Returns:
        pd.DataFrame: The DataFrame containing the data from the file.

    Raises:
        ValueError: If the file format is unsupported or cannot be opened.
    """
    try:
        if file.name.endswith('.xlsx') or file.name.endswith('.xls'):
            df = pd.read_excel(file)
        elif file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            raise ValueError("Format de fichier non pris en charge.")
        return df
    except Exception as e:
        raise ValueError(f"Erreur lors de l'ouverture du fichier : {e}")


def strip_accents(text: str) -> str:
    """
    Removes accents from a string using Unicode normalization.

    Args:
        text (str): Input string containing accented characters.

    Returns:
        str: String with all accents removed.

    Example:
        >>> strip_accents("éèêàç")
        'eeeac'
    """
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def normalize_column_name(col: str) -> str:
    """
    Normalizes a column name by:
    - trimming whitespace,
    - converting to lowercase,
    - removing accents,
    - replacing spaces, hyphens, and multiple underscores with a single underscore,
    - mapping to a standard name using the COLUMN_SYNONYMS dictionary.

    Args:
        col (str): Raw column name.

    Returns:
        str: Normalized column name.

    Example:
        >>> normalize_column_name("claim_id")
        'payment_date'
    """
    col = col.strip().lower()
    col = strip_accents(col)
    col = re.sub(r'[\s\-_]+', '_', col)
    return COLUMN_SYNONYMS.get(col, col)

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize all column names in a DataFrame using the `normalize_column_name` function.

    This includes:
    - Stripping leading/trailing spaces
    - Removing accents and special characters
    - Converting to lowercase
    - Replacing spaces, hyphens, and periods with underscores
    - Mapping known variations to standardized column names (if defined in `COLUMN_SYNONYMS`)

    Args:
        df (pd.DataFrame): The DataFrame whose columns are to be normalized.

    Returns:
        pd.DataFrame: A copy of the DataFrame with normalized column names.
    """
    df.columns = [normalize_column_name(col) for col in df.columns]
    return df


def clean_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans string columns in the DataFrame by:
    - Stripping leading/trailing whitespace
    - Replacing multiple spaces/tabs/newlines inside strings with a single space

    Args:
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: The cleaned DataFrame with normalized text columns.
    """
    for col in df.columns:
        try:
            if col in df.columns and pd.api.types.is_string_dtype(df[col]):
                df.loc[:, col] = (
                    df[col]
                    .str.strip()
                    .str.replace(r'\s+', ' ', regex=True)
                )
        except Exception as e:
            print(f"Error processing column {col}: {e}")
    return df


def replace_invalid_numeric_values(df, column, replacement_value=0):
    """
    Replaces non-numeric values in a column with a specified replacement value.

    Args:
        df (pd.DataFrame): The DataFrame to modify.
        column (str): The name of the column to process.
        replacement_value: The value to replace non-numeric values with.

    Raises:
        KeyError: If the specified column does not exist in the DataFrame.
    """
    if column in df.columns:
        df[column] = df[column].replace({',': '.', '–': '0', '-': '0'}, regex=True)
        df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0) 
    else:
        raise KeyError(f"La colonne '{column}' n'existe pas dans le DataFrame.")



def convert_dates_datetime(df, column, format=None):
    """
    Converts a column to datetime type.

    Args:
        df (pd.DataFrame): The DataFrame to modify.
        column (str): The name of the column to convert.
        format (str): Optional format string for parsing dates.

    Returns:
        pd.DataFrame: The DataFrame with the converted column.
    """
    if column in df.columns:
        column_type = df[column].dtype

        if column_type == 'object':
            df[column] = pd.to_datetime(df[column], format=format, errors='coerce', dayfirst=True)
        elif column_type in ['int64', 'int32']:
            df[column] = pd.to_datetime(df[column], origin='1899-12-30', unit='D', dayfirst=True)
    else:
        raise KeyError(f"La colonne '{column}' n'existe pas dans le DataFrame.")
    return df


def get_date_range(df, column):
    """
    Returns the date range (min, max) for a specified column in a DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to analyze.
        column (str): The name of the column containing dates.

    Returns:
        tuple or None: A tuple containing the minimum and maximum dates, or None if the column is not of datetime type.
    """
    if df.empty:
        return None
    if column not in df.columns:
        raise ValueError(f"La colonne '{column}' n'existe pas dans le DataFrame.")
    if df[column].dtype == 'datetime64[ns]':
        return (df[column].min(), df[column].max())
    else:
        raise TypeError(f"La colonne '{column}' n'est pas de type datetime.")




def get_common_date_range(range1, range2):
    """
    Determines the common date range between two date ranges.

    Args:
        range1 (tuple): A tuple containing the (min_date, max_date) from the first date range.
        range2 (tuple): A tuple containing the (min_date, max_date) from the second date range.

    Returns:
        tuple or None: A tuple containing the common date range (min_common, max_common), or None if there is no common range.
    """
    if range1 is None or range2 is None:
        return None
    min1, max1 = range1
    min2, max2 = range2

    common_min = max(min1, min2)
    common_max = min(max1, max2)

    if common_min <= common_max:
        return (common_min, common_max)
    else:
        return None


def concat_uniques(series, separator=', '):
    """
    Concatenates unique values from a series into a string.

    Args:
        series (pd.Series): The series to process.
        separator (str): The separator to use between unique values.

    Returns:
        str: A string containing the unique values.
    """
    return separator.join(str(x) for x in series.dropna().unique())


def group_statistic_by_sinistre(df):
    """
    Groups data by claim number and aggregates the information.

    Args:
        df (pd.DataFrame): The DataFrame to group.

    Returns:
        pd.DataFrame: A DataFrame grouped by claim number.

    Raises:
        KeyError: If required columns are missing.
    """
    required_columns = ['claim_id', 'beneficiary_name', 'main_insured', 
                        'policy_number', 'partner_name', 'incident_date', 
                        'payment_date', 'claim_status', 'amount_claimed', 'amount_reimbursed']
    
    missing_colums = [col for col in required_columns if col not in df.columns]
    if missing_colums:
        raise KeyError(f"Les colonnes suivantes sont manquantes: {missing_colums}")

    if not all(col in df.columns for col in required_columns):
        raise KeyError("Une ou plusieurs colonnes obligatoires sont manquantes.")

    grouped = df.groupby('claim_id').agg({
        'beneficiary_name': 'first',
        'main_insured': 'first',
        # 'claim_id': 'first',
        'partner_name': 'first',
        'incident_date': 'first',
        'insured_status': 'first',
        'claim_status': 'first',
        'amount_claimed': 'sum',
        'amount_reimbursed': 'sum',
        'act_name': concat_uniques,
        'act_category': concat_uniques,
        'act_family': concat_uniques,
    }).reset_index()
    
    if grouped.duplicated(subset='claim_id').any():
        raise ValueError("Des doublons ont été détectés sur les numéros de sinistre.")
    
    return grouped




def convert_to_upper(df, column):
    """
    Converts all values in a specified column to uppercase.

    Args:
        df (pd.DataFrame): The DataFrame to modify.
        column (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The modified DataFrame.
    """
    if column in df.columns:
        df = df.copy()
        df[column] = df[column].str.upper()
    else:
        raise KeyError(f"La colonne '{column}' n'existe pas dans le DataFrame.")
    return df



def convert_df_to_upper(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts all values in a DataFrame to uppercase.

    Args:
        df (pd.DataFrame): The DataFrame to modify.

    Returns:
        pd.DataFrame: The modified DataFrame.
    """
    # Vérification que df est bien un DataFrame
    if not isinstance(df, pd.DataFrame):
        raise ValueError("L'argument doit être un DataFrame.")

    # print(f"Type de df: {type(df)}")
    # print(f"Colonnes dans df: {df.columns.tolist()}")

    # print(f"Type de df[employer_name]: {df['employer_name'].dtype}")

    for column in df.columns:
        column_data = df.get(column)
        if column_data is not None and column_data.dtype == 'object':
            df.loc[:, column] = column_data.str.upper()  

    return df




def check_conformity(row):
    """
    Checks the conformity of billed and reimbursed amounts based on defined criteria.

    Args:
        row (pd.Series): A row of the DataFrame containing the relevant columns.

    Returns:
        str: 'Conforme' if the row is conforming, 'Non conforme' otherwise.
    """
    if -5 < abs(row["billed_amount_diff"]) < 5 and -5 < abs(row["reimbursement_amount_diff"]) < 5:
        return "Conforme"
    else:
        return "Non conforme"


def df_no_conformity_by_sinistre(df):
    """
    Groups non-conforming data by claim number and aggregates the information.

    Args:
        df (pd.DataFrame): The DataFrame to process.

    Returns:
        pd.DataFrame: A DataFrame of non-conforming data grouped by claim number.
    """
    grouped = df.groupby('claim_id').agg({
        'beneficiary_name': 'first',
        'main_insured': 'first',
        'claim_id': 'first',
        'partner_name': 'first',
        'incident_date': 'first',
        'claim_id': 'first',
        'claim_status': 'first',
        'amount_claimed': 'first',
        'amount_reimbursed': 'first',
        'act_name': concat_uniques,
        'act_category': concat_uniques,
        'act_family': concat_uniques,
        'employer_name': 'first',
        'policy_number': 'first',
        'amount_claimed_recap': 'sum',
        'amount_reimbursed_recap': 'sum',
        'invoice_number': 'first',
        'note': 'first',
    }).reset_index()
    
    # Check for duplicates
    if grouped.duplicated(subset='claim_id').any():
        raise ValueError("Des doublons ont été détectés sur les numéros de sinistre.")
    
    return grouped


def delete_conform_rows(df):
    """
    Deletes conforming rows from the DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to filter.

    Returns:
        pd.DataFrame: The filtered DataFrame without conforming rows.
    """
    df_filtre = df[~((df['amount_claimed'] == df['amount_claimed_recap']) & 
                     (df['amount_reimbursed'] == df['amount_reimbursed_recap']))]
    return df_filtre


def string_to_upper(df):
    """
    Converts all string values in all object-type columns to uppercase.

    Args:
        df (pd.DataFrame): The DataFrame to modify.

    Returns:
        pd.DataFrame: The modified DataFrame.
    """
    df = df.copy()  
    for col in df.columns:
        if df[col].dtype == 'object':  
            df[col] = df[col].str.upper()
    return df


def generate_observation(row):
    """
    Generates observations based on discrepancies in billed and reimbursed amounts.

    Args:
        row (pd.Series): A row of the DataFrame containing the relevant columns.

    Returns:
        str: A string of observations or a message indicating non-conformity.
    """
    observations = []

    ecart_facture = row.get("billed_amount_diff", 0)
    ecart_rembourse = row.get("reimbursed_amount_diff", 0)
    
    if ecart_facture > 0 and ecart_rembourse == 0:
        observations.append("Montant facturé statistique < montant facturé rapprochement.")
    
    if ecart_facture < 0 and ecart_rembourse == 0:
        observations.append("Montant facturé statistique < montant facturé rapprochement.")
    
    if ecart_rembourse > 0 and ecart_facture == 0:
        observations.append("Montant remboursé statistique > montant remboursé rapprochement.")
    
    if ecart_rembourse < 0 and ecart_facture == 0:
        observations.append("Montant remboursé statistique < montant remboursé rapprochement.")
    
    if (ecart_facture > 0 and ecart_rembourse < 0) or (ecart_facture < 0 and ecart_rembourse > 0):
        observations.append("Montants facturés et remboursés non conformes.")

    return "; ".join(observations) if observations else "Non conforme en raison d'écarts."


def generate_no_conformity_excel(df, df_stat, df_recap):
    """
    Generates an Excel file with multiple sheets for non-conformity data.

    Args:
        df (pd.DataFrame): The non-conforming DataFrame.
        df_stat (pd.DataFrame): The statistics DataFrame.
        df_recap (pd.DataFrame): The recap DataFrame.

    Returns:
        str: An error message if an exception occurs, otherwise the file path.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = f'rapports_sinistres_{timestamp}.xlsx'
    file_path = os.path.join('downloads', file_name)

    # Ensure the downloads directory exists
    os.makedirs('downloads', exist_ok=True)

    numeros_sinistre = df['claim_id'].unique()

    df_stat_filtered = df_stat[df_stat['claim_id'].isin(numeros_sinistre)]
    df_recap_filtered = df_recap[df_recap['claim_id'].isin(numeros_sinistre)]

    df.to_excel(file_path, sheet_name='Non Conformités', index=False)
    # df_stat_filtered.to_excel(file_path, sheet_name='Statistiques Filtrées', index=False)
    # df_recap_filtered.to_excel(file_path, sheet_name='Récapitulatif Filtré', index=False)

    if df.empty or df_stat_filtered.empty or df_recap_filtered.empty:
        raise ValueError("Un ou plusieurs DataFrames sont vides.")

    try:
        with pd.ExcelWriter(file_path) as writer:
            df.to_excel(writer, sheet_name='Non Conformités', index=False)
            df_stat_filtered.to_excel(writer, sheet_name='Statistiques Filtrées', index=False)
            df_recap_filtered.to_excel(writer, sheet_name='Récapitulatif Filtré', index=False)
    except Exception as e:
        return str(e)
    return file_path
