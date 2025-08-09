from django.db.models import Sum, Count, Q, Max
from django.core.exceptions import ValidationError
from core.models import Client, Claim, Invoice, InsuredEmployer, Policy, Insured, Partner, Act, ActCategory
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    compute_evolution_rate, format_series_for_multi_line_chart,
    format_top_clients_series, format_top_partners_series, to_date,
    format_top_categories_series, get_granularity_with_points,
    format_date_label, date_label,
)
import logging
import json
import math

def sanitize_float(value):
    """Sanitize float values to ensure JSON serialization compatibility."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return 0.0  # Replace NaN/inf with 0
        return round(value, 2)  # Round to 2 decimal places
    elif isinstance(value, dict):
        return {key: sanitize_float(val) for key, val in value.items()}
    elif isinstance(value, list):
        return [sanitize_float(val) for val in value]
    else:
        return value

logger = logging.getLogger(__name__)


class ClientStatisticsService:
    """
    Service to generate statistics for a specific client over a given period.
    """
    
    def __init__(self, client_id, date_start_str, date_end_str):
        """
        Initializes the service with the basic parameters.
        
        Args:
            client_id (int): Client ID
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.client_id = int(client_id)
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            # self.granularity = get_granularity(self.date_start, self.date_end)

            self.granularity, self.granularity_points = get_granularity_with_points(
                self.date_start, self.date_end
            )
            
            # Génération des labels pour les graphiques
            self.granularity_labels = [
                format_date_label(point, self.granularity) 
                for point in self.granularity_points
            ]
            
            # Génération des timestamps pour ApexCharts
            self.granularity_timestamps = [
                int(point.timestamp() * 1000) 
                for point in self.granularity_points
            ]

            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for ClientStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")
    
    def _setup_base_filters(self):
        """
        Configures the base filters for queries with optimized querysets.
        """
        try:
            # Base client queryset with select_related
            self.client = Client.objects.select_related('country').filter(
                id=self.client_id
            ).first()
            
            # Validate that client exists
            if not self.client:
                logger.warning(f"No client found for client_id: {self.client_id}")
                raise ValidationError(f"Client with ID {self.client_id} does not exist")
            
            # Optimized policies queryset
            self.policies = Policy.objects.select_related('client').filter(
                client_id=self.client_id
            )
            self.policy_ids = list(self.policies.values_list('id', flat=True))
            
            # Get insured IDs for this client via InsuredEmployer relationship
            insured_ids = list(
                InsuredEmployer.objects.filter(employer=self.client_id)
                .values_list('insured_id', flat=True)
            )
            
            # Optimized claims queryset with proper joins
            # Claims can be linked via insured OR policy, so we use both approaches
            self.claims = Claim.objects.select_related(
                'invoice', 'policy__client', 'insured', 'partner'
            ).filter(
                Q(insured_id__in=insured_ids) | Q(policy__client_id=self.client_id),
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Standard logging for monitoring
            logger.info(f"Client {self.client_id}: {len(insured_ids)} insured, {self.policies.count()} policies, {self.claims.count()} claims")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_policies_evolution(self):
        """
        Calculates the evolution of the number of policies.
        
        Returns:
            list: Time series of the number of policies
        """
        try:
            result = list(
                self.policies.filter(creation_date__range=(self.date_start, self.date_end))
                .annotate(period=self.trunc('creation_date'))
                .values('period')
                .annotate(value=Count('id'))
                .order_by('period')
            )
            
            # Keep counts as integers
            for point in result:
                point['value'] = int(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_policies_evolution: {e}")
            return []
    
    def get_premium_evolution(self):
        """
        Calculates the evolution of the total premium for this client.
        Uses the client's premium history or current premium.
        
        Returns:
            list: Time series of premiums
        """
        try:
            # Try to get premium history first
            from core.models import ClientPrimeHistory
            
            # Check if there's premium history data
            history_exists = ClientPrimeHistory.objects.filter(
                client_id=self.client_id,
                date__range=(self.date_start, self.date_end)
            ).exists()
            
            if history_exists:
                # Use premium history data
                result = list(
                    ClientPrimeHistory.objects.filter(
                        client_id=self.client_id,
                        date__range=(self.date_start, self.date_end)
                    )
                    .annotate(period=self.trunc('date'))
                    .values('period')
                    .annotate(value=Sum('prime'))
                    .order_by('period')
                )
                
                # Convert to float for monetary values
                for point in result:
                    point['value'] = float(point['value'] or 0)
                
                return result
            else:
                # Use client's current premium for each period
                periods = generate_periods(self.date_start, self.date_end, self.granularity)
                result = []
                
                client_premium = float(self.client.prime or 0)
                for period in periods:
                    result.append({
                        'period': period,
                        'value': client_premium
                    })
                
                return result
                
        except Exception as e:
            logger.error(f"Error in get_premium_evolution: {e}")
            return []
    
    def get_reimbursed_amount_evolution(self):
        """
        Calculates the evolution of the reimbursed amount.
        
        Returns:
            list: Time series of reimbursed amounts
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            
            # Convert to float for monetary values
            for point in result:
                point['value'] = float(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_reimbursed_amount_evolution: {e}")
            return []
    
    def get_claimed_amount_evolution(self):
        """
        Calculates the evolution of the claimed amount.
        
        Returns:
            list: Time series of claimed amounts
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Sum('invoice__claimed_amount'))
                .order_by('period')
            )
            
            # Convert to float for monetary values
            for point in result:
                point['value'] = float(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_claimed_amount_evolution: {e}")
            return []
    
    def get_partners_evolution(self):
        """
        Calculates the evolution of the number of distinct partners.
        
        Returns:
            list: Time series of the number of partners
        """
        try:
            result = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Count('invoice__provider', distinct=True))
                .order_by('period')
            )
            
            # Keep counts as integers
            for point in result:
                point['value'] = int(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_partners_evolution: {e}")
            return []
    
    def get_sp_ratio_evolution(self, premium_series, reimbursed_series):
        """
        Calculates the evolution of the S/P ratio (Claims/Premiums).
        
        Args:
            premium_series (list): Series of premiums
            reimbursed_series (list): Series of reimbursements
            
        Returns:
            list: Time series of S/P ratios
        """
        try:
            premiums_by_period = {point['period']: float(point['value'] or 0) for point in premium_series}
            reimbursed_by_period = {point['period']: float(point['value'] or 0) for point in reimbursed_series}
            all_periods = sorted(set(premiums_by_period.keys()) | set(reimbursed_by_period.keys()))
            
            ratio_series = []
            for period in all_periods:
                premium = premiums_by_period.get(period, 0)
                reimbursement = reimbursed_by_period.get(period, 0)
                
                # Handle division by zero
                if premium == 0:
                    ratio = None if reimbursement == 0 else float('inf')
                else:
                    ratio = reimbursement / premium
                    
                ratio_series.append({"period": period, "value": ratio})
            
            return ratio_series
        except Exception as e:
            logger.error(f"Error in get_sp_ratio_evolution: {e}")
            return []
    
    def get_primary_insured_evolution(self):
        """
        Calculates the evolution of the number of principal insured.
        
        Returns:
            list: Time series of principal insured
        """
        try:
            result = list(
                InsuredEmployer.objects.filter(
                    employer=self.client_id,
                    role='primary',
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            
            # Keep counts as integers
            for point in result:
                point['value'] = int(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_primary_insured_evolution: {e}")
            return []
    
    def get_total_insured_evolution(self):
        """
        Calculates the evolution of the total number of insured.
        
        Returns:
            list: Time series of total insured
        """
        try:
            result = list(
                InsuredEmployer.objects.filter(
                    employer=self.client_id,
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            
            # Keep counts as integers
            for point in result:
                point['value'] = int(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_total_insured_evolution: {e}")
            return []
    
    def get_insured_by_role_evolution(self):
        """
        Calculates the evolution of the number of insured by role type.
        
        Returns:
            dict: Dictionary of series by role
        """
        roles = ['primary', 'spouse', 'child']
        insured_by_role = {}
        
        for role in roles:
            try:
                result = list(
                    InsuredEmployer.objects.filter(
                        employer=self.client_id,
                        role=role,
                        insured__creation_date__range=(self.date_start, self.date_end)
                    )
                    .annotate(period=self.trunc('insured__creation_date'))
                    .values('period')
                    .annotate(value=Count('insured_id', distinct=True))
                    .order_by('period')
                )
                
                # Keep counts as integers
                for point in result:
                    point['value'] = int(point['value'] or 0)
                
                insured_by_role[role] = result
            except Exception as e:
                logger.error(f"Error in get_insured_by_role_evolution for role {role}: {e}")
                insured_by_role[role] = []
        
        return insured_by_role
    
    def get_consumption_by_role_timeseries(self):
        """
        Calculates the evolution of consumption by insured role.
        
        Returns:
            dict: Dictionary of series by role
        """
        try:
            claims_by_role = list(
                self.claims.annotate(period=self.trunc('settlement_date'))
                .values('period', 'insured__insured_clients__role')
                .annotate(value=Sum('invoice__reimbursed_amount'))
                .order_by('period', 'insured__insured_clients__role')
            )
            
            # Structure the data by role
            consumption_by_role = {}
            for claim in claims_by_role:
                role = claim['insured__insured_clients__role']
                if role not in consumption_by_role:
                    consumption_by_role[role] = []
                consumption_by_role[role].append({
                    'period': claim['period'],
                    'value': float(claim['value'] or 0)
                })
            
            return consumption_by_role
        except Exception as e:
            logger.error(f"Error in get_consumption_by_role_timeseries: {e}")
            return {}
    
    def get_top_partners_consumption(self, limit=5):
        """
        Calculates the top partners with the highest consumption.
        
        Args:
            limit (int): Number of partners to return
            
        Returns:
            list: Data of top partners with their time series
        """
        try:
            # Identification of top partners
            top_partners = list(
                self.claims.values('invoice__provider_id')
                .annotate(total_consumption=Sum('invoice__reimbursed_amount'))
                .order_by('-total_consumption')[:limit]
            )
            
            top_partner_ids = [p['invoice__provider_id'] for p in top_partners]
            partner_names = {p.id: p.name for p in Partner.objects.filter(id__in=top_partner_ids)}

            # Generation of time series for each top partner
            top_partners_series = []
            for partner_id in top_partner_ids:
                partner_claims = self.claims.filter(invoice__provider_id=partner_id)
                partner_series = list(
                    partner_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                
                # Convert to float
                for point in partner_series:
                    point['value'] = float(point['value'] or 0)
                
                top_partners_series.append({
                    "partner_id": partner_id,
                    "partner_name": partner_names.get(partner_id, str(partner_id)),
                    "series": partner_series
                })

            
            return top_partners_series
        except Exception as e:
            logger.error(f"Error in get_top_partners_consumption: {e}")
            return []
    
    def get_top_partners_table(self, limit=5):
        """
        Gets the top partners table data.
        
        Args:
            limit (int): Number of partners to return
            
        Returns:
            list: Table data of top partners
        """
        try:
            top_partners_qs = list(
                self.claims.values('partner_id')
                .annotate(
                    reimbursed=Sum('invoice__reimbursed_amount'),
                    claimed=Sum('invoice__claimed_amount')
                )
                .order_by('-reimbursed')[:limit]
            )
            
            partner_ids = [p['partner_id'] for p in top_partners_qs]
            partner_objs = {p.id: p for p in Partner.objects.filter(id__in=partner_ids)}
            
            top_partners_table = []
            for p in top_partners_qs:
                partner_obj = partner_objs.get(p['partner_id'])
                top_partners_table.append({
                    "id": p['partner_id'],
                    "name": partner_obj.name if partner_obj else str(p['partner_id']),
                    "claimed": float(p.get('claimed', 0) or 0),
                    "reimbursed": float(p.get('reimbursed', 0) or 0)
                })
            
            return top_partners_table
        except Exception as e:
            logger.error(f"Error in get_top_partners_table: {e}")
            return []
    
    def get_top_acts_consumption(self, limit=5):
        """
        Calculates the top acts with the highest consumption.
        
        Args:
            limit (int): Number of acts to return
            
        Returns:
            list: Data of top acts with their time series
        """
        try:
            top_acts = list(
                self.claims.values('act_id')
                .annotate(total_consumption=Sum('invoice__reimbursed_amount'))
                .order_by('-total_consumption')[:limit]
            )
            top_act_ids = [a['act_id'] for a in top_acts]
            act_names = {a.id: a.label for a in Act.objects.filter(id__in=top_act_ids)}

            top_acts_series = []
            for act_id in top_act_ids:
                act_claims = self.claims.filter(act_id=act_id)
                act_series = list(
                    act_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in act_series:
                    point['value'] = float(point['value'] or 0)
                top_acts_series.append({
                    "act_id": act_id,
                    "act_name": act_names.get(act_id, str(act_id)),
                    "series": act_series
                })
            return top_acts_series
        except Exception as e:
            logger.error(f"Error in get_top_acts_consumption: {e}")
            return []
    
    def get_top_categories_consumption(self, limit=5):
        """
        Calculates the top act categories with the highest consumption.
        
        Args:
            limit (int): Number of categories to return
            
        Returns:
            list: Data of top categories with their time series
        """
        try:
            top_categories = list(
                self.claims.filter(
                    act__isnull=False,
                    act__family__category__isnull=False
                )
                .values('act__family__category')
                .annotate(total_consumption=Sum('invoice__reimbursed_amount'))
                .order_by('-total_consumption')[:limit]
            )
            
            top_category_ids = [c['act__family__category'] for c in top_categories]
            category_names = {c.id: c.label for c in ActCategory.objects.filter(id__in=top_category_ids)}

            top_categories_series = []
            for category_id in top_category_ids:
                category_claims = self.claims.filter(act__family__category=category_id)
                category_series = list(
                    category_claims.annotate(period=self.trunc('settlement_date'))
                    .values('period')
                    .annotate(value=Sum('invoice__reimbursed_amount'))
                    .order_by('period')
                )
                for point in category_series:
                    point['value'] = float(point['value'] or 0)
                top_categories_series.append({
                    "category_id": category_id,
                    "category_name": category_names.get(category_id, str(category_id)),
                    "series": category_series
                })
            return top_categories_series
        except Exception as e:
            logger.error(f"Error in get_top_categories_consumption: {e}")
            return []
    

    
    def get_complete_statistics(self):
        """
        Generates all statistics for the client in an optimized manner.
        
        Returns:
            dict: Complete dictionary of statistics
        """
        # Collecting all base series
        policies_series = self.get_policies_evolution()
        premium_series = self.get_premium_evolution()
        reimbursed_series = self.get_reimbursed_amount_evolution()
        claimed_series = self.get_claimed_amount_evolution()
        partners_series = self.get_partners_evolution()
        primary_insured_series = self.get_primary_insured_evolution()
        total_insured_series = self.get_total_insured_evolution()
        insured_by_role = self.get_insured_by_role_evolution()
        top_partners_series = self.get_top_partners_consumption()
        top_partners_table = self.get_top_partners_table()
        top_categories_series = self.get_top_categories_consumption()
        
        # Calculating the S/P ratio
        sp_ratio_series = self.get_sp_ratio_evolution(premium_series, reimbursed_series)
        
        # Generating complete periods
        periods = generate_periods(self.date_start, self.date_end, self.granularity)
        
        # Filling series with all periods
        policies_series_full = fill_full_series(periods, policies_series)
        premium_series_full = fill_full_series(periods, premium_series)
        reimbursed_series_full = fill_full_series(periods, reimbursed_series)
        claimed_series_full = fill_full_series(periods, claimed_series)
        primary_insured_series_full = fill_full_series(periods, primary_insured_series)
        total_insured_series_full = fill_full_series(periods, total_insured_series)
        
        # Converting to pairs for ApexCharts
        policies_series_pairs = serie_to_pairs(policies_series_full)
        premium_series_pairs = serie_to_pairs(premium_series_full)
        reimbursed_series_pairs = serie_to_pairs(reimbursed_series_full)
        claimed_series_pairs = serie_to_pairs(claimed_series_full)
        partners_series_pairs = serie_to_pairs(partners_series)
        sp_ratio_series_pairs = serie_to_pairs(sp_ratio_series)
        primary_insured_series_pairs = serie_to_pairs(primary_insured_series_full)
        total_insured_series_pairs = serie_to_pairs(total_insured_series_full)
        
        # Formatting series by insured type
        role_labels = {
            'primary': 'Primary Insured',
            'spouse': 'Spouse Insured',
            'child': 'Child Insured',
        }
        insured_by_role_series = format_series_for_multi_line_chart(
            insured_by_role, periods, self.granularity, role_labels
        )
        
        # Formatting top partners
        top_partners_series_multi, top_partners_categories = format_top_partners_series(
            top_partners_series, periods, self.granularity
        )

        top_categories_series_multi, top_categories_series_categories = format_top_categories_series(
            top_categories_series, periods, self.granularity
        )
        
        # Calculating actual values (max of series over period)
        actual_values = self._calculate_actual_values(
            policies_series, premium_series, reimbursed_series, claimed_series_full,
            primary_insured_series, total_insured_series
        )
        
        # Calculating evolution rates  
        evolution_rates = self._calculate_evolution_rates(
            policies_series, premium_series, reimbursed_series, claimed_series,
            primary_insured_series, total_insured_series
        )
        
        # Prepare the complete statistics dictionary
        statistics = {
            "granularity": self.granularity,
            "granularity_timestamps": self.granularity_timestamps,
            "granularity_labels": self.granularity_labels,
            
            # Time series
            "policies_series": policies_series_pairs,
            "premium_series": premium_series_pairs,
            "reimbursed_amount_series": reimbursed_series_pairs,
            "claimed_amount_series": claimed_series_pairs,
            "partners_series": partners_series_pairs,
            "sp_ratio_series": sp_ratio_series_pairs,
            "primary_insured_series": primary_insured_series_pairs,
            "total_insured_series": total_insured_series_pairs,
            "insured_by_role_series": insured_by_role_series,
            "top_partners_consumption_series": top_partners_series_multi,
            "top_partners_consumption_categories": top_partners_categories,
            "top_partners_table": top_partners_table,
            "top_categories" : top_categories_series_multi,
            
            # Actual values
            **actual_values,
            
            # Evolution rates
            **evolution_rates
        }
        
        # Sanitize all float values to prevent JSON serialization errors
        return sanitize_float(statistics)
    
    def _calculate_actual_values(self, policies_series, premium_series, reimbursed_series, 
                                claimed_series_full, primary_insured_series, total_insured_series):
        """
        Calculates the maximum values of various metrics over the period.
        
        Returns:
            dict: Dictionary of maximum values
        """
        try:
            def safe_max_int(series):
                values = [int(point['value'] or 0) for point in series if point.get('value') is not None]
                return max(values) if values else 0
            
            def safe_max_float(series):
                values = [float(point['value'] or 0) for point in series if point.get('value') is not None]
                return max(values) if values else 0.0
            
            return {
                "actual_policies_value": safe_max_int(policies_series),
                "actual_premium_value": safe_max_float(premium_series),
                "actual_reimbursed_amount_value": safe_max_float(reimbursed_series),
                "actual_claimed_amount_value": safe_max_float(claimed_series_full),
                "actual_primary_insured_value": safe_max_int(primary_insured_series),
                "actual_total_insured_value": safe_max_int(total_insured_series),
            }
        except Exception as e:
            logger.error(f"Error calculating actual values: {e}")
            return {
                "actual_policies_value": 0,
                "actual_premium_value": 0.0,
                "actual_reimbursed_amount_value": 0.0,
                "actual_claimed_amount_value": 0.0,
                "actual_primary_insured_value": 0,
                "actual_total_insured_value": 0,
            }
    
    def _calculate_evolution_rates(self, policies_series, premium_series, reimbursed_series,
                                  claimed_series, primary_insured_series, total_insured_series):
        """
        Calculates the evolution rates of various metrics.
        
        Returns:
            dict: Dictionary of evolution rates
        """
        try:
            return {
                "policies_evolution_rate": compute_evolution_rate(policies_series),
                "premium_evolution_rate": compute_evolution_rate(premium_series),
                "reimbursed_amount_evolution_rate": compute_evolution_rate(reimbursed_series),
                "claimed_amount_evolution_rate": compute_evolution_rate(claimed_series),
                "primary_insured_evolution_rate": compute_evolution_rate(primary_insured_series),
                "total_insured_evolution_rate": compute_evolution_rate(total_insured_series),
            }
        except Exception as e:
            logger.error(f"Error calculating evolution rates: {e}")
            return {
                "policies_evolution_rate": 0.0,
                "premium_evolution_rate": 0.0,
                "reimbursed_amount_evolution_rate": 0.0,
                "claimed_amount_evolution_rate": 0.0,
                "primary_insured_evolution_rate": 0.0,
                "total_insured_evolution_rate": 0.0,
            }



class ClientStatisticListService:
    """
    Service to generate statistics list for all clients in a country over a given period.
    """
    
    def __init__(self, country_id, date_start_str, date_end_str):
        """
        Initialize the service with country ID and date range.
        
        Args:
            country_id (int): ID of the country
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.country_id = country_id
        self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
        
        try:
            self._setup_base_filters()
        except Exception as e:
            logger.error(f"Error initializing ClientStatisticListService: {e}")
            raise
    
    def _setup_base_filters(self):
        """
        Set up base querysets for clients and related data.
        """
        try:
            # Base clients queryset for the country
            self.clients = Client.objects.select_related('country').filter(
                country_id=self.country_id
            )
            
            # Validate that country exists
            if not self.clients.exists():
                logger.warning(f"No clients found for country_id: {self.country_id}")
            
            # Standard logging for monitoring
            logger.info(f"Country {self.country_id}: {self.clients.count()} clients found")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_clients_statistics_list(self):
        """
        Generate statistics list for all clients in the country.
        
        Returns:
            list: List of client statistics dictionaries
        """
        try:
            results = []
            
            for client in self.clients:
                client_stats = self._get_client_statistics(client)
                results.append(client_stats)
            
            # Sanitize all float values to prevent JSON serialization errors
            return sanitize_float(results)
            
        except Exception as e:
            logger.error(f"Error generating clients statistics list: {e}")
            return []
    
    def _get_client_statistics(self, client):
        """
        Get statistics for a single client.
        
        Args:
            client: Client object
            
        Returns:
            dict: Client statistics
        """
        try:
            # Get policies count
            nb_policies = Policy.objects.filter(client=client).count()
            
            # Get insured employees for this client
            insured_links = InsuredEmployer.objects.select_related('insured').filter(
                employer=client
            )
            nb_primary = insured_links.filter(role='primary').count()
            nb_total = insured_links.count()
            
            # Get insured IDs for claims filtering
            insured_ids = list(insured_links.values_list('insured_id', flat=True))
            
            # Get claims for this client in the date range
            # Use both insured and policy relationships like in ClientStatisticsService
            claims = Claim.objects.select_related('invoice').filter(
                Q(insured_id__in=insured_ids) | Q(policy__client_id=client.id),
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Calculate consumption and reimbursement totals
            consumption_data = claims.aggregate(
                total_consumption=Sum('invoice__claimed_amount'),
                total_reimbursement=Sum('invoice__reimbursed_amount')
            )
            
            total_consumption = float(consumption_data['total_consumption'] or 0)
            total_reimbursement = float(consumption_data['total_reimbursement'] or 0)
            
            return {
                "client_id": client.id,
                "client_name": client.name,
                "contact": client.contact,
                "nb_policies": nb_policies,
                "nb_primary_insured": nb_primary,
                "nb_total_insured": nb_total,
                "total_consumption": total_consumption,
                "total_reimbursement": total_reimbursement
            }
            
        except Exception as e:
            logger.error(f"Error calculating statistics for client {client.id}: {e}")
            return {
                "client_id": client.id,
                "client_name": client.name,
                "contact": client.contact or "",
                "nb_policies": 0,
                "nb_primary_insured": 0,
                "nb_total_insured": 0,
                "total_consumption": 0.0,
                "total_reimbursement": 0.0
            }



class GlobalClientsListService:
    """
    Service to generate statistics list for all clients in the database over a given period.
    Each client includes their country information.
    """
    
    def __init__(self, date_start_str, date_end_str):
        """
        Initialize the service with date range.
        
        Args:
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
        
        try:
            self._setup_base_filters()
        except Exception as e:
            logger.error(f"Error initializing AllClientsListService: {e}")
            raise
    
    def _setup_base_filters(self):
        """
        Set up base querysets for all clients and related data.
        """
        try:
            # Base clients queryset for all clients with their country
            self.clients = Client.objects.select_related('country').all()
            
            # Standard logging for monitoring
            logger.info(f"All clients: {self.clients.count()} clients found")
            
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")
    
    def get_all_clients_statistics_list(self):
        """
        Generate statistics list for all clients in the database.
        
        Returns:
            list: List of client statistics dictionaries with country information
        """
        try:
            results = []
            
            for client in self.clients:
                client_stats = self._get_client_statistics(client)
                results.append(client_stats)
            
            # Sanitize all float values to prevent JSON serialization errors
            return sanitize_float(results)
            
        except Exception as e:
            logger.error(f"Error generating all clients statistics list: {e}")
            return []
    
    def _get_client_statistics(self, client):
        """
        Get statistics for a single client including country information.
        
        Args:
            client: Client object
            
        Returns:
            dict: Client statistics with country information
        """
        try:
            # Get policies count
            nb_policies = Policy.objects.filter(client=client).count()
            
            # Get insured employees for this client
            insured_links = InsuredEmployer.objects.select_related('insured').filter(
                employer=client
            )
            nb_primary = insured_links.filter(role='primary').count()
            nb_total = insured_links.count()
            
            # Get insured IDs for claims filtering
            insured_ids = list(insured_links.values_list('insured_id', flat=True))
            
            # Get claims for this client in the date range
            # Use both insured and policy relationships like in ClientStatisticsService
            claims = Claim.objects.select_related('invoice').filter(
                Q(insured_id__in=insured_ids) | Q(policy__client_id=client.id),
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            
            # Calculate consumption and reimbursement totals
            consumption_data = claims.aggregate(
                total_consumption=Sum('invoice__claimed_amount'),
                total_reimbursement=Sum('invoice__reimbursed_amount')
            )
            
            total_consumption = float(consumption_data['total_consumption'] or 0)
            total_reimbursement = float(consumption_data['total_reimbursement'] or 0)
            
            return {
                "client_id": client.id,
                "client_name": client.name,
                "contact": client.contact,
                "country_id": client.country.id if client.country else None,
                "country_name": client.country.name if client.country else None,
                "nb_policies": nb_policies,
                "nb_primary_insured": nb_primary,
                "nb_total_insured": nb_total,
                "total_consumption": total_consumption,
                "total_reimbursement": total_reimbursement
            }
            
        except Exception as e:
            logger.error(f"Error calculating statistics for client {client.id}: {e}")
            return {
                "client_id": client.id,
                "client_name": client.name,
                "contact": client.contact or "",
                "country_id": client.country.id if client.country else None,
                "country_name": client.country.name if client.country else None,
                "nb_policies": 0,
                "nb_primary_insured": 0,
                "nb_total_insured": 0,
                "total_consumption": 0.0,
                "total_reimbursement": 0.0
            }


class GlobalClientStatisticsService:
    """
    Service to generate minimal global client statistics (4 essential metrics only).
    
    This service provides simple, current statistics about clients across all countries
    with only the most essential metrics: total clients, countries count, total premium, and S/P ratio.
    """

    def __init__(self):
        """
        Initializes the service without date parameters for current totals only.
        """
        try:
            self._setup_base_querysets()
        except Exception as e:
            logger.error(f"Error initializing GlobalClientStatisticsService: {e}")
            raise ValidationError(f"Error initializing service: {e}")

    def _setup_base_querysets(self):
        """
        Sets up optimized base querysets for essential client data only.
        """
        try:
            # Base querysets for all clients
            self.clients = Client.objects.all()
            self.client_ids = list(self.clients.values_list('id', flat=True))

            # Related querysets for premium calculation
            self.policies = Policy.objects.select_related('client').filter(
                client__in=self.client_ids
            )
            self.policy_ids = list(self.policies.values_list('id', flat=True))

            # Claims data for S/P ratio calculation
            self.claims = Claim.objects.select_related(
                'invoice', 'policy__client', 'insured'
            ).filter(
                policy__in=self.policy_ids,
                invoice__isnull=False
            )

            # Invoices data for claimed amount calculation
            self.invoices = Invoice.objects.select_related(
                'provider', 'insured'
            ).filter(
                insured__insured_clients__employer__in=self.client_ids
            )

        except Exception as e:
            logger.error(f"Error setting up base querysets: {e}")
            raise ValidationError(f"Error setting up querysets: {e}")

    def get_total_clients_count(self):
        """
        Get the total number of clients across all countries.
        
        Returns:
            int: Total number of clients
        """
        try:
            return self.clients.count()
        except Exception as e:
            logger.error(f"Error getting total clients count: {e}")
            return 0

    def get_countries_count(self):
        """
        Get the number of countries with clients.
        
        Returns:
            int: Number of countries with clients
        """
        try:
            return self.clients.values('country').distinct().count()
        except Exception as e:
            logger.error(f"Error getting countries count: {e}")
            return 0

    def get_total_premium_amount(self):
        """
        Get the total premium amount across all clients.
        
        Returns:
            float: Total premium amount
        """
        try:
            total = self.clients.aggregate(total=Sum('prime'))['total']
            return float(total or 0)
        except Exception as e:
            logger.error(f"Error getting total premium amount: {e}")
            return 0.0

    def get_total_claimed_amount(self):
        """
        Get the total claimed amount across all clients.
        
        Returns:
            float: Total claimed amount
        """
        try:
            total = self.invoices.aggregate(total=Sum('claimed_amount'))['total']
            return float(total or 0)
        except Exception as e:
            logger.error(f"Error getting total claimed amount: {e}")
            return 0.0

    def _calculate_sp_ratio(self):
        """
        Calculate the S/P ratio (Sinistres/Primes) - claims to premium ratio.
        
        Returns:
            float: S/P ratio as percentage
        """
        try:
            total_premium = self.get_total_premium_amount()
            if total_premium == 0:
                return 0.0
            
            total_claimed = self.get_total_claimed_amount()
            return round((total_claimed / total_premium) * 100, 2)
        except Exception as e:
            logger.error(f"Error calculating S/P ratio: {e}")
            return 0.0

    def get_complete_statistics(self):
        """
        Get minimal global client statistics with only 4 essential metrics.
        
        Returns:
            dict: Minimal statistics dictionary with 4 key metrics
        """
        try:
            return {
                # Essential metrics only
                "total_clients": self.get_total_clients_count(),
                "countries_count": self.get_countries_count(),
                "total_premium": self.get_total_premium_amount(),
                "sp_ratio": self._calculate_sp_ratio(),
            }
        except Exception as e:
            logger.error(f"Error getting complete statistics: {e}")
            return {}


class CountryClientStatisticsService:
    """
    Service to generate minimal country-specific client statistics (4 essential metrics only).
    
    This service provides simple, current statistics about clients for a specific country
    with only the most essential metrics: total clients, total premium, and S/P ratio.
    """

    def __init__(self, country_id):
        """
        Initializes the service for a specific country.
        
        Args:
            country_id (int): Country ID
        """
        try:
            self.country_id = int(country_id)
            self._setup_base_querysets()
        except Exception as e:
            logger.error(f"Error initializing CountryClientStatisticsService: {e}")
            raise ValidationError(f"Error initializing service: {e}")

    def _setup_base_querysets(self):
        """
        Sets up optimized base querysets for essential client data for a specific country.
        """
        try:
            # Base querysets for clients in the specific country
            self.clients = Client.objects.filter(country_id=self.country_id)
            self.client_ids = list(self.clients.values_list('id', flat=True))

            # Related querysets for premium calculation
            self.policies = Policy.objects.select_related('client').filter(
                client__in=self.client_ids
            )
            self.policy_ids = list(self.policies.values_list('id', flat=True))

            # Claims data for S/P ratio calculation
            self.claims = Claim.objects.select_related(
                'invoice', 'policy__client', 'insured'
            ).filter(
                policy__in=self.policy_ids,
                invoice__isnull=False
            )

            # Invoices data for claimed amount calculation
            self.invoices = Invoice.objects.select_related(
                'provider', 'insured'
            ).filter(
                insured__insured_clients__employer__in=self.client_ids
            )

        except Exception as e:
            logger.error(f"Error setting up base querysets: {e}")
            raise ValidationError(f"Error setting up querysets: {e}")

    def get_total_clients_count(self):
        """
        Get the total number of clients in the specific country.
        
        Returns:
            int: Total number of clients in the country
        """
        try:
            return self.clients.count()
        except Exception as e:
            logger.error(f"Error getting total clients count: {e}")
            return 0

    def get_total_premium_amount(self):
        """
        Get the total premium amount for clients in the specific country.
        
        Returns:
            float: Total premium amount for the country
        """
        try:
            total = self.clients.aggregate(total=Sum('prime'))['total']
            return float(total or 0)
        except Exception as e:
            logger.error(f"Error getting total premium amount: {e}")
            return 0.0

    def get_total_claimed_amount(self):
        """
        Get the total claimed amount for clients in the specific country.
        
        Returns:
            float: Total claimed amount for the country
        """
        try:
            total = self.invoices.aggregate(total=Sum('claimed_amount'))['total']
            return float(total or 0)
        except Exception as e:
            logger.error(f"Error getting total claimed amount: {e}")
            return 0.0

    def get_total_insured_count(self):
        """
        Get the total number of insured people in the specific country.
        
        Returns:
            int: Total number of insured people in the country
        """
        try:
            return self.insured_employers.values('insured').distinct().count()
        except Exception as e:
            logger.error(f"Error getting total insured count: {e}")
            return 0

    def _calculate_sp_ratio(self):
        """
        Calculate the S/P ratio (Sinistres/Primes) for the specific country.
        
        Returns:
            float: S/P ratio as percentage
        """
        try:
            total_premium = self.get_total_premium_amount()
            if total_premium == 0:
                return 0.0
            
            total_claimed = self.get_total_claimed_amount()
            return round((total_claimed / total_premium) * 100, 2)
        except Exception as e:
            logger.error(f"Error calculating S/P ratio: {e}")
            return 0.0

    def get_complete_statistics(self):
        """
        Get minimal country-specific client statistics with only 4 essential metrics.
        
        Returns:
            dict: Minimal statistics dictionary with 4 key metrics
        """
        try:
            return {
                # Essential metrics for country
                "total_clients": self.get_total_clients_count(),
                "total_insured": self.get_total_insured_count(),
                "total_premium": self.get_total_premium_amount(),
                "sp_ratio": self._calculate_sp_ratio(),
            }
        except Exception as e:
            logger.error(f"Error getting complete statistics: {e}")
            return {}
