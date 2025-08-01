from django.db.models import Sum, Count
from django.core.exceptions import ValidationError
from core.models import Client, Claim, InsuredEmployer, Policy, Invoice
from countries.models import Country
from .base import (
    get_granularity, get_trunc_function, parse_date_range,
    generate_periods, fill_full_series, serie_to_pairs,
    compute_evolution_rate, format_series_for_multi_line_chart,
    format_top_clients_series, format_countries_consumption_series
)
import logging

logger = logging.getLogger(__name__)

class GlobalStatisticsService:
    """
    Service to generate global statistics (all countries) over a given period.
    """

    def __init__(self, date_start_str, date_end_str):
        """
        Initializes the service with the basic parameters.
        Args:
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            self.granularity = get_granularity(self.date_start, self.date_end)
            self.trunc = get_trunc_function(self.granularity)
            self._setup_base_filters()
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for GlobalStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def _setup_base_filters(self):
        """
        Configures the base filters for queries with optimized querysets (no country filter).
        """
        try:
            self.clients = Client.objects.all()
            self.client_ids = list(self.clients.values_list('id', flat=True))

            self.policies = Policy.objects.select_related('client').filter(
                client__in=self.client_ids
            )
            self.policy_ids = list(self.policies.values_list('id', flat=True))

            self.claims = Claim.objects.select_related(
                'invoice', 'policy__client', 'insured'
            ).filter(
                policy__in=self.policy_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
        except Exception as e:
            logger.error(f"Error setting up base filters: {e}")
            raise ValidationError(f"Error setting up filters: {e}")

    def get_clients_timeseries(self):
        """
        Calculates the evolution of the number of clients.
        
        Returns:
            list: Time series of the number of clients
        """
        try:
            result = list(
                self.clients.filter(creation_date__range=(self.date_start, self.date_end))
                .annotate(period=self.trunc('creation_date'))
                .values('period')
                .annotate(value=Count('id'))
                .order_by('period')
            )        
            for point in result:
                point['value'] = int(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_clients_timeseries: {e}")
            return []
    
    def get_prime_timeseries(self):
        """
        Calculates the evolution of the total premium.
        
        Returns:
            list: Time series of premiums
        """
        try:
            result = list(
                self.clients.filter(creation_date__range=(self.date_start, self.date_end))
                .annotate(period=self.trunc('creation_date'))
                .values('period')
                .annotate(value=Sum('prime'))
                .order_by('period')
            )
            for point in result:
                point['value'] = float(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_prime_timeseries: {e}")
            return []
    
    def get_reimbursed_amount_timeseries(self):
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
            for point in result:
                point['value'] = float(point['value'] or 0)       
            return result
        except Exception as e:
            logger.error(f"Error in get_reimbursed_amount_timeseries: {e}")
            return []
    
    def get_claimed_amount_timeseries(self):
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
            for point in result:
                point['value'] = float(point['value'] or 0)
            
            return result
        except Exception as e:
            logger.error(f"Error in get_claimed_amount_timeseries: {e}")
            return []
    
    def get_partners_timeseries(self):
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
            for point in result:
                point['value'] = int(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_partners_timeseries: {e}")
            return []
    
    def get_sp_ratio_timeseries(self, prime_series, reimbursed_series):
        """
        Calculates the evolution of the S/P ratio (Claims/Premiums).
        
        Args:
            prime_series (list): Series of premiums
            reimbursed_series (list): Series of reimbursements
            
        Returns:
            list: Time series of S/P ratios
        """
        primes_by_period = {point['period']: float(point['value'] or 0) for point in prime_series}
        rembourse_by_period = {point['period']: float(point['value'] or 0) for point in reimbursed_series}
        all_periods = sorted(set(primes_by_period.keys()) | set(rembourse_by_period.keys()))
        
        ratio_series = []
        for period in all_periods:
            prime = primes_by_period.get(period, 0)
            remboursement = rembourse_by_period.get(period, 0)
            ratio = remboursement / prime if prime else None
            ratio_series.append({"period": period, "value": ratio})
        
        return ratio_series
    
    def get_primary_insured_timeseries(self):
        """
        Calculates the evolution of the number of principal insured.
        
        Returns:
            list: Time series of principal insured
        """
        try:
            result = list(
                InsuredEmployer.objects.filter(
                    employer_id__in=self.client_ids,
                    role='primary',
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            for point in result:
                point['value'] = int(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_primary_insured_timeseries: {e}")
            return []

    
    def get_total_insured_timeseries(self):
        """
        Calculates the evolution of the total number of insured.
        
        Returns:
            list: Time series of total insured
        """
        try:
            result = list(
                InsuredEmployer.objects.filter(
                    employer_id__in=self.client_ids,
                    insured__creation_date__range=(self.date_start, self.date_end)
                )
                .annotate(period=self.trunc('insured__creation_date'))
                .values('period')
                .annotate(value=Count('insured_id', distinct=True))
                .order_by('period')
            )
            for point in result:
                point['value'] = int(point['value'] or 0)
            return result
        except Exception as e:
            logger.error(f"Error in get_total_insured_timeseries: {e}")
            return []
    
    def get_insured_by_role_timeseries(self):
        """
        Calculates the evolution of the number of insured by role type.
        
        Returns:
            dict: Dictionary of series by role
        """
        roles = ['primary', 'spouse', 'child', 'other']
        insured_by_role = {}
        
        for role in roles:
            try:
                series = list(
                    InsuredEmployer.objects.filter(
                        employer_id__in=self.client_ids,
                        role=role,
                        insured__creation_date__range=(self.date_start, self.date_end)
                    )
                    .annotate(period=self.trunc('insured__creation_date'))
                    .values('period')
                    .annotate(value=Count('insured_id', distinct=True))
                    .order_by('period')
                )
                for point in series:
                    point['value'] = int(point['value'] or 0)
                insured_by_role[role] = series
            except Exception as e:
                logger.error(f"Error in get_insured_by_role_timeseries for role {role}: {e}")
                insured_by_role[role] = []
        return insured_by_role
    
    def get_top_clients_consumption(self, limit=5):
        """
        Calculates the top clients with the highest consumption.
        
        Args:
            limit (int): Number of clients to return
            
        Returns:
            list: Data of top clients with their time series
        """
        top_clients = list(
            self.claims.values('policy__client_id')
            .annotate(total_consumption=Sum('invoice__reimbursed_amount'))
            .order_by('-total_consumption')[:limit]
        )
        top_client_ids = [c['policy__client_id'] for c in top_clients]
        client_names = {c.id: c.name for c in Client.objects.filter(id__in=top_client_ids)}

        top_clients_series = []
        for client_id in top_client_ids:
            client_claims = self.claims.filter(policy__client_id=client_id)
            client_series = list(
                client_claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            for point in client_series:
                point['value'] = float(point['value'] or 0)
            top_clients_series.append({
                "client_id": client_id,
                "client_name": client_names.get(client_id, str(client_id)),
                "series": client_series
            })
        return top_clients_series
    
    def get_countries_consumption_multiline_series(self, limit=None):
        """
        Returns a multi-line chart data structure showing the evolution of consumption (reimbursed amount)
        for each country over the selected period, following the same structure as get_top_clients_consumption.

        Returns:
            list: Data of countries with their time series
        """
        countries = list(Country.objects.all())
        country_ids = [c.id for c in countries]
        country_names = {c.id: c.name for c in countries}
        
        print(f"Countries: {country_names}")
        print(f"country_names.get(country_id, str(country_id)): {country_names.get(1, 'Unknown Country')}")

        countries_series = []
        for country_id in country_ids:
            client_ids = list(Client.objects.filter(country_id=country_id).values_list('id', flat=True))
            policy_ids = list(Policy.objects.filter(client_id__in=client_ids).values_list('id', flat=True))
            country_claims = Claim.objects.filter(
                policy_id__in=policy_ids,
                settlement_date__range=(self.date_start, self.date_end),
                invoice__isnull=False
            )
            country_series = list(
                country_claims.annotate(period=self.trunc('settlement_date'))
                .values('period')
                .annotate(value=Sum('invoice__reimbursed_amount'))
                .order_by('period')
            )
            for point in country_series:
                point['value'] = float(point['value'] or 0)
            countries_series.append({
                "country_id": country_id,
                "country_name": country_names.get(country_id, str(country_id)),
                "series": country_series
            })
        return countries_series

    def get_complete_statistics(self):
        """
        Generates all statistics for the country in an optimized manner.
        
        Returns:
            dict: Complete dictionary of statistics
        """
        # Collecting all base series
        clients_series = self.get_clients_timeseries()
        primes_series = self.get_prime_timeseries()
        reimbursed_series = self.get_reimbursed_amount_timeseries()
        claimed_series = self.get_claimed_amount_timeseries()
        partners_series = self.get_partners_timeseries()
        primary_insured_series = self.get_primary_insured_timeseries()
        total_insured_series = self.get_total_insured_timeseries()
        insured_by_role = self.get_insured_by_role_timeseries()
        top_clients_series = self.get_top_clients_consumption()
        countries_consumption_series = self.get_countries_consumption_multiline_series()

        print(f'country series: {countries_consumption_series}')
        
        # Calculating the S/P ratio
        sp_ratio_series = self.get_sp_ratio_timeseries(primes_series, reimbursed_series)
        
        # Generating complete periods
        periods = generate_periods(self.date_start, self.date_end, self.granularity)
        
        # Filling series with all periods
        clients_series_full = fill_full_series(periods, clients_series)
        primes_series_full = fill_full_series(periods, primes_series)
        reimbursed_series_full = fill_full_series(periods, reimbursed_series)
        claimed_series_full = fill_full_series(periods, claimed_series)
        primary_insured_series_full = fill_full_series(periods, primary_insured_series)
        total_insured_series_full = fill_full_series(periods, total_insured_series)
        
        # Converting to pairs for ApexCharts
        clients_series_pairs = serie_to_pairs(clients_series_full)
        primes_series_pairs = serie_to_pairs(primes_series_full)
        reimbursed_series_pairs = serie_to_pairs(reimbursed_series_full)
        claimed_series_pairs = serie_to_pairs(claimed_series_full)
        primary_insured_series = serie_to_pairs(primary_insured_series_full)
        total_insured_series_pairs = serie_to_pairs(total_insured_series_full)
        partners_series_pairs = serie_to_pairs(partners_series)
        sp_ratio_series_pairs = serie_to_pairs(sp_ratio_series)
        
        # Formatting series by insured type
        role_labels = {
            'primary': 'Assurés  Principaux',
            'spouse': 'Assurés Conjoints',
            'child': 'Assurés Enfants',
        }
        insured_by_role_series = format_series_for_multi_line_chart(
            insured_by_role, periods, self.granularity, role_labels
        )
        
        # Formatting top clients
        top_clients_series_multi, top_clients_categories = format_top_clients_series(
            top_clients_series, periods, self.granularity
        )

        # Countries consumption multi-line chart
        countries_consumption_series_multi, countries_consumption_categories = format_countries_consumption_series(
            countries_consumption_series, periods, self.granularity
        )

        print(f"countries_consumption_series_multi: {countries_consumption_series_multi}")

        # Calculating actual values
        actual_values = self._calculate_actual_values(
            clients_series_full, primes_series_full, reimbursed_series_full, claimed_series_full,
            primary_insured_series_full, total_insured_series_full
        )
        
        # Calculating evolution rates  
        evolution_rates = self._calculate_evolution_rates(
            clients_series_full, primes_series_full, reimbursed_series_full, claimed_series_full,
            primary_insured_series_full, total_insured_series_full
        )
        
        return {
            "granularity": self.granularity,
            "clients_series": clients_series_pairs,
            "prime_globale_series": primes_series_pairs,
            "montant_rembourse_series": reimbursed_series_pairs,
            "montant_reclame_series": claimed_series_pairs,
            "partners_series": partners_series_pairs,
            "sp_ratio_series": sp_ratio_series_pairs,
            "nb_assures_principaux_series": primary_insured_series,
            "nb_assures_total_series": total_insured_series_pairs,
            "nb_assures_par_type_series": insured_by_role_series,
            "top5_clients_conso_series": top_clients_series_multi,
            "top5_clients_conso_categories": top_clients_categories,
            "countries_consumption_multiline_series": countries_consumption_series_multi,
            "countries_consumption_categories": countries_consumption_categories,
            **actual_values,
            **evolution_rates
        }    
    def _calculate_actual_values(self, clients_series_full, primes_series_full, reimbursed_series, 
                                claimed_series_full, primary_insured_series, total_insured_series):
        """
        Calculates the peak (max) value for each metric over the period.

        Returns:
            dict: Dictionary of peak values
        """
        def max_value(series):
            values = [point['value'] for point in series if point['value'] is not None]
            return max(values) if values else 0

        return {
            "actual_nb_clients_value": int(max_value(clients_series_full)),
            "actual_prime_globale_value": float(max_value(primes_series_full)),
            "actual_montant_rembourse_value": float(max_value(reimbursed_series)),
            "actual_montant_reclame_value": float(max_value(claimed_series_full)),
            "actual_nb_assures_principaux_value": float(max_value(primary_insured_series)),
            "actual_nb_assures_total_value": float(max_value(total_insured_series)),
        }
    
    def _calculate_evolution_rates(self, clients_series, primes_series, reimbursed_series,
                                  claimed_series, primary_insured_series, total_insured_series):
        """
        Calculates the evolution rates of various metrics.
        
        Returns:
            dict: Dictionary of evolution rates
        """
        return {
            "clients_evolution_rate": compute_evolution_rate(clients_series),
            "prime_globale_evolution_rate": compute_evolution_rate(primes_series),
            "montant_rembourse_evolution_rate": compute_evolution_rate(reimbursed_series),
            "montant_reclame_evolution_rate": compute_evolution_rate(claimed_series),
            "nb_assures_principaux_evolution_rate": compute_evolution_rate(primary_insured_series),
            "nb_assures_total_evolution_rate": compute_evolution_rate(total_insured_series),
        }




class CountriesListStatisticsService:
    """
    Service to retrieve country-level statistics, including:
    - Country name
    - Total premium (prime globale)
    - Total consumption (consommation globale)
    - S/P ratio (ratio of premium to consumption)
    - Number of insured individuals
    - Number of clients

    Methods:
        get_countries_statistics():
            Computes and returns a list of dictionaries, each containing the above statistics for every country.
            Aggregates data from related Client, InsuredEmployer, Claim, and Invoice models.
            Filters data within the date range provided at initialization.
    """

    def __init__(self, date_start_str, date_end_str):
        """
        Initializes the service with optional date filters.
        Args:
            date_start_str (str): Start date in YYYY-MM-DD format
            date_end_str (str): End date in YYYY-MM-DD format
        """
        try:
            if date_start_str and date_end_str:
                self.date_start, self.date_end = parse_date_range(date_start_str, date_end_str)
            else:
                self.date_start, self.date_end = None, None
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameters for CountriesListStatisticsService: {e}")
            raise ValidationError(f"Invalid parameters: {e}")

    def get_countries_statistics(self):
        from django.db.models import Sum, Count

        countries = Country.objects.all()
        results = []
        for country in countries:
            clients = Client.objects.filter(country=country)
            if self.date_start and self.date_end:
                clients = clients.filter(creation_date__range=(self.date_start, self.date_end))
            nb_clients = clients.count()
            prime_globale = clients.aggregate(total=Sum('prime'))['total'] or 0

            client_ids = clients.values_list('id', flat=True)

            # Nombre d'assurés du pays (distincts)
            insured_qs = InsuredEmployer.objects.filter(employer_id__in=client_ids)
            if self.date_start and self.date_end:
                insured_qs = insured_qs.filter(insured__creation_date__range=(self.date_start, self.date_end))
            nb_assures = insured_qs.values('insured_id').distinct().count()

            # Consommation globale : somme des montants remboursés des claims dont la policy appartient à un client du pays
            claims_qs = Claim.objects.filter(policy__client_id__in=client_ids)
            if self.date_start and self.date_end:
                claims_qs = claims_qs.filter(settlement_date__range=(self.date_start, self.date_end))
            claim_invoice_ids = claims_qs.values_list('invoice_id', flat=True)
            consommation_globale = Invoice.objects.filter(id__in=claim_invoice_ids).aggregate(total=Sum('reimbursed_amount'))['total'] or 0

            # Ratio S/P
            ratio_sp = float(prime_globale) / float(consommation_globale) if consommation_globale else None

            results.append({
                'country_id': country.id,
                'country_name': country.name,
                'prime_globale': float(prime_globale),
                'consommation_globale': float(consommation_globale),
                'ratio_sp': float(ratio_sp) if ratio_sp is not None else None,
                'nb_assures': nb_assures,
                'nb_clients': nb_clients,
            })
        return results
