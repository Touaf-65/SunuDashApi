import pandas as pd
from utils.functions import (get_date_range, get_common_date_range, group_statistic_by_sinistre,
                            convert_to_upper, check_conformity, delete_conform_rows, generate_observation
 )
class ComparisonService:
    @staticmethod
    def get_common_date(df_stat, df_recap):
        recap_range = get_date_range(df_recap, 'payment_date')
        stat_range = get_date_range(df_stat, 'payment_date')

        common_range = get_common_date_range(stat_range, recap_range)

        return common_range

    @staticmethod
    def rename_recap_columns(df_recap):
        df_recap.rename(columns={
            "amount_claimed": "amount_claimed_recap",
            "amount_reimbursed": "amount_reimbursed_recap"
        }, inplace=True)

        return df_recap

    @staticmethod
    def compare_dataframes(df_stat, df_recap, common_range):
        filtered_df_stat = df_stat[(df_stat['payment_date'] >= common_range[0]) & (df_stat['payment_date'] <= common_range[1])]
        filtered_df_recap = df_recap[(df_recap['payment_date'] >= common_range[0]) & (df_recap['payment_date'] <= common_range[1])]

        df_stat_grouped = group_statistic_by_sinistre(filtered_df_stat)
        df_stat_grouped = convert_to_upper(df_stat_grouped, "claim_id")
        filtered_df_recap = convert_to_upper(filtered_df_recap, "claim_id")

        df_comparaison = pd.merge(df_stat_grouped, filtered_df_recap, on="claim_id", how="inner")
        df_comparaison.drop_duplicates(inplace=True)

        df_comparaison["billed_amount_diff"] = df_comparaison["amount_claimed"] - df_comparaison["amount_claimed_recap"]
        df_comparaison["reimbursement_amount_diff"] = df_comparaison["amount_reimbursed"] - df_comparaison["amount_reimbursed_recap"]
        df_comparaison["conformity"] = df_comparaison.apply(check_conformity, axis=1)

        return df_comparaison

    @staticmethod
    def extract_non_conformity(df_comparaison):
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
        conform_claim_ids = df_conformes['claim_id'].unique()
        df_stat_filtered = df_stat[(df_stat['payment_date'] >= common_range[0]) & (df_stat['payment_date'] <= common_range[1])]
        df_final_conformes = df_stat_filtered[df_stat_filtered['claim_id'].isin(conform_claim_ids)].copy()
        
        return {
            "non_conformes": df_non_conformes,
            "conformes": df_final_conformes,
            "common_range": common_range
        }