import pandas as pd
from importer.utils.functions import (get_date_range, get_common_date_range, group_statistic_by_sinistre,
                            convert_to_upper, check_conformity, delete_conform_rows, generate_observation
 )
class ComparisonService:
    @staticmethod
    def get_common_date(df_stat, df_recap):
        """
        Computes the common date range between two DataFrames.

        Args:
            df_stat (pd.DataFrame): The 'statistic' DataFrame.
            df_recap (pd.DataFrame): The 'recap' DataFrame.

        Returns:
            tuple or None: A tuple containing the common date range, or None if there is no common range.
        """

        recap_range = get_date_range(df_recap, 'payment_date')

        # print(f"Range date de recap: {recap_range}")

        stat_range = get_date_range(df_stat, 'payment_date')

        # print(f"Range date de stat: {stat_range}")

        common_range = get_common_date_range(stat_range, recap_range)

        return common_range

    @staticmethod
    def rename_recap_columns(df_recap):
        """
        Renames the columns of a DataFrame to distinguish them from the columns of the statistic DataFrame.

        Args:
            df_recap (pd.DataFrame): The 'recap' DataFrame.

        Returns:
            pd.DataFrame: The DataFrame with renamed columns.
        """
        df_recap.rename(columns={
            "amount_claimed": "amount_claimed_recap",
            "amount_reimbursed": "amount_reimbursed_recap"
        }, inplace=True)

        return df_recap

    @staticmethod
    def compare_dataframes(df_stat, df_recap, common_range):      
        """
        Compares two DataFrames for conformity based on a common date range.

        Filters and processes the 'statistic' and 'recap' DataFrames to identify
        differences in claimed and reimbursed amounts. The function groups the
        statistic data by claim, converts claim IDs to uppercase for consistency,
        and merges the data on claim IDs. It calculates the differences in billed
        and reimbursement amounts and assesses conformity for each claim.

        Args:
            df_stat (pd.DataFrame): The 'statistic' DataFrame containing claim details.
            df_recap (pd.DataFrame): The 'recap' DataFrame containing additional claim details.
            common_range (tuple): A tuple containing the common date range (start, end)
                for filtering the data.

        Returns:
            pd.DataFrame: A DataFrame containing the compared results with columns
            for billed amount difference, reimbursement amount difference, and
            conformity status.
        """

        filtered_df_stat = df_stat[(df_stat['payment_date'] >= common_range[0]) & (df_stat['payment_date'] <= common_range[1])]
        filtered_df_recap = df_recap[(df_recap['payment_date'] >= common_range[0]) & (df_recap['payment_date'] <= common_range[1])]


        df_stat_grouped = group_statistic_by_sinistre(filtered_df_stat)
        df_stat_grouped = convert_to_upper(df_stat_grouped, "claim_id")
        filtered_df_recap = convert_to_upper(filtered_df_recap, "claim_id")

        filtered_df_recap = filtered_df_recap.rename(columns={
            'amount_claimed': 'amount_claimed_recap',
            'amount_reimbursed': 'amount_reimbursed_recap'
        })

        required_columns = ["amount_claimed", "amount_reimbursed", "claim_id"]
        missing_columns = [col for col in required_columns if col not in df_stat_grouped.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns in df_stat_grouped: {missing_columns}")


        df_comparison = pd.merge(
            df_stat_grouped, 
            filtered_df_recap, 
            on="claim_id", 
            how="inner",
            suffixes=('', '_recap')
        )

        df_comparison["billed_amount_diff"] = df_comparison["amount_claimed"] - df_comparison["amount_claimed_recap"]
        df_comparison["reimbursement_amount_diff"] = df_comparison["amount_reimbursed"] - df_comparison["amount_reimbursed_recap"]

        
        required_after_merge = ["amount_claimed", "amount_claimed_recap", 
                              "amount_reimbursed", "amount_reimbursed_recap"]
        missing_after_merge = [col for col in required_after_merge if col not in df_comparison.columns]
        
        if missing_after_merge:
            raise ValueError(f"Missing required columns after merge: {missing_after_merge}")


        for col in ['amount_claimed', 'amount_claimed_recap', 'amount_reimbursed', 'amount_reimbursed_recap']:
            non_numeric = pd.to_numeric(df_comparison[col], errors='coerce').isna()
            if non_numeric.any():
                print(f"\n=== WARNING: Non-numeric values found in {col} ===")
                print(df_comparison[non_numeric][['claim_id', col]].head())
                df_comparison[col] = pd.to_numeric(df_comparison[col], errors='coerce').fillna(0)


        df_comparison["conformity"] = df_comparison.apply(check_conformity, axis=1)

        return df_comparison

    @staticmethod
    def extract_non_conformity(df_comparaison):
        """
        Extracts non-conforming data from a DataFrame of compared data.

        The function filters non-conforming claims, checks for deleted conforming claims,
        and adds an observation column to the non-conforming DataFrame.

        Args:
            df_comparaison (pd.DataFrame): The DataFrame containing the compared data.

        Returns:
            tuple: A tuple containing the non-conforming DataFrame and the conforming DataFrame.
        """
        df_non_conformes = df_comparaison[df_comparaison['conformity'] == 'Non conforme'].copy()
        df_conformes = df_comparaison[df_comparaison['conformity'] == 'Conforme'].copy()

        if not df_non_conformes.empty:
            deleted_conformes = df_non_conformes[
                (df_non_conformes['amount_claimed'] == df_non_conformes['amount_claimed_recap']) &
                (df_non_conformes['amount_reimbursed'] == df_non_conformes['amount_reimbursed_recap'])
            ]

            df_non_conformes = delete_conform_rows(df_non_conformes)

            df_conformes = pd.concat([df_conformes, deleted_conformes]).drop_duplicates(subset=["claim_id"])

            if not df_non_conformes.empty:
                df_non_conformes['observation'] = df_non_conformes.apply(generate_observation, axis=1)
        
        return df_non_conformes, df_conformes

    @staticmethod
    def export_results(df_stat, common_range, df_non_conformes, df_conformes):
        """
        Exports the results of the comparison.

        Args:
            df_stat (pd.DataFrame): The 'statistic' DataFrame containing claim details.
            common_range (tuple): A tuple containing the common date range (start, end)
                for filtering the data.
            df_non_conformes (pd.DataFrame): The DataFrame containing non-conforming claims.
            df_conformes (pd.DataFrame): The DataFrame containing conforming claims.

        Returns:
            dict: A dictionary containing the non-conforming DataFrame, the conforming DataFrame,
            and the common date range.
        """
        conform_claim_ids = df_conformes['claim_id'].unique()
        df_stat_filtered = df_stat[(df_stat['payment_date'] >= common_range[0]) & (df_stat['payment_date'] <= common_range[1])]
        df_final_conformes = df_stat_filtered[df_stat_filtered['claim_id'].isin(conform_claim_ids)].copy()
        
        return {
            "non_conformes": df_non_conformes,
            "conformes": df_final_conformes,
            "common_range": common_range
        }