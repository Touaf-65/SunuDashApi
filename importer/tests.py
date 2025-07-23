# pyright: ignore[reportMissingImports]

import pandas as pd
import pytest
from io import BytesIO
from datetime import datetime
from .utils.functions import (
    open_excel_csv,
    strip_accents,
    normalize_column_name,
    normalize_columns,
    clean_text_columns,
    replace_invalid_numeric_values,
    convert_dates_datetime,
    get_date_range,
    get_common_date_range,
    concat_uniques,
    group_statistic_by_sinistre,
    convert_to_upper,
    check_conformity,
    df_no_conformity_by_sinistre,
    delete_conform_rows,
    string_to_upper,
    generate_observation,
    generate_no_conformity_excel
)

# Test pour open_excel_csv
# def test_open_excel_csv():
#     # Créer un DataFrame et l'enregistrer en tant que fichier Excel
#     df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
#     excel_file = BytesIO()
#     df.to_excel(excel_file, index=False)
#     excel_file.seek(0)

#     result = open_excel_csv(excel_file)
#     assert isinstance(result, pd.DataFrame)
#     assert list(result.columns) == ['A', 'B']

#     # Tester avec un fichier CSV
#     csv_file = BytesIO()
#     df.to_csv(csv_file, index=False)
#     csv_file.seek(0)

#     result = open_excel_csv(csv_file)
#     assert isinstance(result, pd.DataFrame)
#     assert list(result.columns) == ['A', 'B']

#     # Tester avec un format non supporté
#     with pytest.raises(ValueError, match="Format de fichier non pris en charge."):
#         open_excel_csv(BytesIO(b"not a file"))

def test_strip_accents():
    assert strip_accents("éèêàç") == "eeeac"
    assert strip_accents("café") == "cafe"
    assert strip_accents("") == ""

def test_normalize_column_name():
    global COLUMN_SYNONYMS
    COLUMN_SYNONYMS = {'claim_id': 'payment_date'}

    assert normalize_column_name("  Claim_ID ") == "claim_id"
    assert normalize_column_name("Unknown") == "unknown"

def test_normalize_columns():
    df = pd.DataFrame(columns=["  Claim_ID ", "Beneficiary-Name"])
    normalized_df = normalize_columns(df)
    assert list(normalized_df.columns) == ['claim_id', 'beneficiary_name']

def test_clean_text_columns():
    df = pd.DataFrame({'text': ['  Hello   World ', '  Test \n\t String  ']})
    cleaned_df = clean_text_columns(df)
    assert cleaned_df['text'].iloc[0] == 'Hello World'
    assert cleaned_df['text'].iloc[1] == 'Test String'

def test_replace_invalid_numeric_values():
    df = pd.DataFrame({'numbers': ['1', '2', 'invalid', '3.5', '–', '-']})
    replace_invalid_numeric_values(df, 'numbers')
    assert df['numbers'].tolist() == [1, 2, 0, 3.5, 0, 0]

    with pytest.raises(KeyError, match="La colonne 'non_existent' n'existe pas dans le DataFrame."):
        replace_invalid_numeric_values(df, 'non_existent')

def test_convert_dates_datetime():
    df = pd.DataFrame({'dates': ['2021-01-01', '2021-02-01', 'invalid']})
    convert_dates_datetime(df, 'dates')
    assert df['dates'].iloc[0] == pd.Timestamp('2021-01-01')
    assert pd.isna(df['dates'].iloc[2])

    with pytest.raises(KeyError, match="La colonne 'non_existent' n'existe pas dans le DataFrame."):
        convert_dates_datetime(df, 'non_existent')

def test_get_date_range():
    df = pd.DataFrame({'dates': [pd.Timestamp('2021-01-01'), pd.Timestamp('2021-02-01')]})
    date_range = get_date_range(df, 'dates')
    assert date_range == (pd.Timestamp('2021-01-01'), pd.Timestamp('2021-02-01'))

    with pytest.raises(ValueError, match="La colonne 'non_existent' n'existe pas dans le DataFrame."):
        get_date_range(df, 'non_existent')

def test_get_common_date_range():
    range1 = (pd.Timestamp('2021-01-01'), pd.Timestamp('2021-02-01'))
    range2 = (pd.Timestamp('2021-01-15'), pd.Timestamp('2021-01-30'))
    common_range = get_common_date_range(range1, range2)
    assert common_range == (pd.Timestamp('2021-01-15'), pd.Timestamp('2021-01-30'))

    assert get_common_date_range(None, range2) is None

def test_concat_uniques():
    series = pd.Series(['a', 'b', 'a', 'c', 'b'])
    result = concat_uniques(series, separator='; ')
    assert result == 'a; b; c'

# def test_group_statistic_by_sinistre():
#     df = pd.DataFrame({
#         'claim_id': [1, 1, 2, 3],
#         'beneficiary_name': ['Alice', 'Alice', 'Bob', 'Charlie'],
#         'main_insured': ['Insured1', 'Insured1', 'Insured2', 'Insured3'],
#         'policy_number': ['PN1', 'PN1', 'PN2', 'PN3'],
#         'partner_name': ['Partner1', 'Partner1', 'Partner2', 'Partner3'],
#         'incident_date': ['2021-01-01', '2021-01-01', '2021-01-02', '2021-01-03'],
#         'payment_date': ['2021-01-05', '2021-01-05', '2021-01-06', '2021-01-07'],
#         'claim_status': ['Closed', 'Closed', 'Open', 'Closed'],
#         'amount_claimed': [100, 150, 200, 350],
#         'amount_reimbursed': [80, 120, 150, 200],
#         'act_name': ['Act1', 'Act1', 'Act2', 'Act3'],
#         'act_category': ['Category1', 'Category1', 'Category2', 'Category3'],
#         'act_family': ['Family1', 'Family1', 'Family2', 'Family3']
#     })
#     grouped = group_statistic_by_sinistre(df)
#     assert len(grouped) == 3  # 3 claims
#     assert grouped['amount_claimed'].iloc[1] == 250  # Total for claim_id 1

    # with pytest.raises(KeyError, match="Une ou plusieurs colonnes obligatoires sont manquantes."):
    #     group_statistic_by_sinistre(pd.DataFrame({'claim_id': [1]}))  # Missing required columns

def test_convert_to_upper():
    df = pd.DataFrame({'text': ['hello', 'world']})
    converted_df = convert_to_upper(df, 'text')
    assert converted_df['text'].tolist() == ['HELLO', 'WORLD']

    with pytest.raises(KeyError, match="La colonne 'non_existent' n'existe pas dans le DataFrame."):
        convert_to_upper(df, 'non_existent')

def test_check_conformity():
    row_conforme = pd.Series({"Écart facturé": 3, "Écart remboursé": 2})
    row_non_conforme = pd.Series({"Écart facturé": 10, "Écart remboursé": 12})
    
    assert check_conformity(row_conforme) == "Conforme"
    assert check_conformity(row_non_conforme) == "Non conforme"

# Test pour df_no_conformity_by_sinistre
# def test_df_no_conformity_by_sinistre():
#     df = pd.DataFrame({
#         'claim_id': [1, 1, 2],
#         'beneficiary_name': ['Alice', 'Alice', 'Bob'],
#         'main_insured': ['Insured1', 'Insured1', 'Insured2'],
#         'policy_number': ['PN1', 'PN1', 'PN2'],
#         'partner_name': ['Partner1', 'Partner1', 'Partner2'],
#         'incident_date': ['2021-01-01', '2021-01-01', '2021-01-02'],
#         'payment_date': ['2021-01-05', '2021-01-05', '2021-01-06'],
#         'claim_status': ['Closed', 'Closed', 'Open'],
#         'amount_claimed': [100, 100, 200],
#         'amount_reimbursed': [80, 80, 150],
#     })
#     grouped = df_no_conformity_by_sinistre(df)
#     assert len(grouped) == 2  # 2 claims
#     assert grouped['claim_id'].iloc[0] == 1  # First claim

def test_delete_conform_rows():
    df = pd.DataFrame({
        'amount_claimed': [100, 200],
        'Total facturé rapprochement': [100, 200],
        'amount_reimbursed': [80, 150],
        'Total remboursé rapprochement': [80, 150],
    })
    filtered_df = delete_conform_rows(df)
    assert filtered_df.empty  # All rows are conforming

    df_non_conform = pd.DataFrame({
        'amount_claimed': [100, 250],
        'Total facturé rapprochement': [100, 200],
        'amount_reimbursed': [80, 200],
        'Total remboursé rapprochement': [80, 150],
    })
    filtered_non_conform = delete_conform_rows(df_non_conform)
    assert len(filtered_non_conform) == 1  # One non-conforming row remains

def test_string_to_upper():
    df = pd.DataFrame({'text': ['hello', 'world']})
    upper_df = string_to_upper(df)
    assert upper_df['text'].tolist() == ['HELLO', 'WORLD']

# def test_generate_observation():
#     row_conforme = pd.Series({"Écart facturé": 3, "Écart remboursé": 2})
#     row_non_conforme = pd.Series({"Écart facturé": 10, "Écart remboursé": 12})
    
#     assert generate_observation(row_conforme) == "Non conforme en raison d'écarts."
#     assert "Montants facturés et remboursés non conformes." in generate_observation(row_non_conforme)

# def test_generate_no_conformity_excel():
#     df = pd.DataFrame({
#         'claim_id': [1, 2],
#         'beneficiary_name': ['Alice', 'Bob'],
#         'main_insured': ['Insured1', 'Insured2'],
#         'policy_number': ['PN1', 'PN2'],
#         'partner_name': ['Partner1', 'Partner2'],
#         'incident_date': ['2021-01-01', '2021-01-02'],
#         'payment_date': ['2021-01-05', '2021-01-06'],
#         'claim_status': ['Closed', 'Open'],
#         'amount_claimed': [100, 200],
#         'amount_reimbursed': [80, 150],
#     })
#     df_stat = df.copy()
#     df_recap = df.copy()

#     # Créer un répertoire temporaire pour éviter des erreurs de chemin
#     import os
#     if not os.path.exists('downloads'):
#         os.makedirs('downloads')

#     path = generate_no_conformity_excel(df, df_stat, df_recap)
#     assert path.endswith('.xlsx')  # Check if it returns a path to an Excel file

#     # Check for empty DataFrames
#     with pytest.raises(ValueError, match="Un ou plusieurs DataFrames sont vides."):
#         generate_no_conformity_excel(pd.DataFrame(), df_stat, df_recap)
