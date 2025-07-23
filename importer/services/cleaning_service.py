from utils.functions import normalize_columns, replace_invalid_numeric_values, clean_text_columns, convert_dates_datetime, convert_df_to_upper
import pandas as pd

class CleaningService:
    @staticmethod
    def clean_recap_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans and standardizes the 'recap' (aggregated summary) DataFrame by:
        - Normalizing column names
        - Removing fully empty rows
        - Cleaning text fields
        - Converting payment_date to datetime
        - Normalizing numeric values in key columns
        - Removing rows without a valid claim_id (id_sinistre)

        Args:
            df (pd.DataFrame): Raw DataFrame loaded from the 'recap' file.

        Returns:
            pd.DataFrame: Cleaned and standardized DataFrame.
        """
        df = normalize_columns(df)  
        df.dropna(how='all', inplace=True)
        df = df.drop_duplicates()

        df = clean_text_columns(df)  

        df = convert_df_to_upper(df)

        if 'payment_date' in df.columns:
            df = convert_dates_datetime(df, 'payment_date', format='%d/%m/%Y')

        for col in ['amount_claimed', 'amount_reimbursed']:
            if col in df.columns:
                replace_invalid_numeric_values(df, col)

        if 'claim_id' in df.columns:
            df = df[df['claim_id'].notna() & (df['claim_id'] != '')]

        return df
    

    @staticmethod
    def clean_stat_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans and standardizes the 'statistic' DataFrame by:
        - Normalizing column names
        - Removing fully empty and duplicate rows
        - Removing irrelevant columns
        - Cleaning text fields
        - Converting date columns to datetime
        - Normalizing numeric values

        Args:
            df (pd.DataFrame): Raw DataFrame loaded from the 'stat' file.

        Returns:
            pd.DataFrame: Cleaned and standardized DataFrame.
        """
        df = normalize_columns(df)
        df.dropna(how='all', inplace=True)
        df.drop_duplicates(inplace=True)

        columns_to_drop = [
            'unnamed_1', 'broker_name', 'broker_sunu_id', 'adresse_du_partenaire'
        ]
        existing_columns = [col for col in columns_to_drop if col in df.columns]
        df.drop(columns=existing_columns, inplace=True)

        df = clean_text_columns(df)

        df = convert_df_to_upper(df)

        for col in ['date_de_reglement', 'date_de_sinistre', 'payment_date', 'incident_date']:
            if col in df.columns:
                df = convert_dates_datetime(df, col, format='%d/%m/%Y')

        for col in ['montant_facture', 'montant_rembourse', 'amount_claimed', 'amount_reimbursed']:
            if col in df.columns:
                replace_invalid_numeric_values(df, col)

        if 'claim_id' in df.columns:
            df = df[df['claim_id'].notna() & (df['claim_id'] != '')]

        return df
