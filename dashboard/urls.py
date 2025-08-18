from django.urls import path
from .views import (
    # Global Statistics
    GlobalStatisticsDetailView, 
    GlobalCountriesListStatisticsView,
    GlobalClientStatisticsListView,
    GlobalClientStatisticsDetailView,
    GlobalPartnerStatisticsView,
    GlobalPartnerListStatisticsView,
    GlobalPolicyListView,
    GlobalPolicyStatisticsView,
    GlobalPolicyStatisticsDetailView,
    SpecificPolicyStatisticsDetailView,
    
    # Country Statistics
    CountryStatisticsDetailView,
    ClientStatisticsDetailView,
    SpecificClientStatisticsDetailView,
    CountryClientStatisticsListView,
    CountryPartnerStatisticsView,
    CountryPartnerListStatisticsView,
    CountryInsuredStatisticsView,
    CountryInsuredListStatisticsView,
    CountryFamilyStatisticsView,
    CountryFamilyListView,
    ClientFamilyStatisticsView,
    ClientFamilyListView,
    CountryPolicyStatisticsView,
    
    # Territorial Statistics
    CountryPolicyListView,
    
    # Client Statistics
    ClientPartnerStatisticsView,
    ClientPartnerListStatisticsView,
    
    # Policy Statistics
    PolicyPartnerStatisticsView,
    PolicyPartnerListStatisticsView,
    
    # Partner Statistics
    PartnerStatisticsView,
)

urlpatterns = [
    # Global Statistics
    path('global/statistics/', GlobalStatisticsDetailView.as_view(), name='global-statistics-detail'),
    path('global/countries/statistics/', GlobalCountriesListStatisticsView.as_view(), name='global-countries-list-statistics'),
    path('global/clients/statistics/', GlobalClientStatisticsDetailView.as_view(), name='global-client-statistics'),
    path('global/clients/list/', GlobalClientStatisticsListView.as_view(), name='global-client-list'),
    path('global/partners/statistics/', GlobalPartnerStatisticsView.as_view(), name='global-partner-statistics'),
    path('global/partners/list/', GlobalPartnerListStatisticsView.as_view(), name='global-partner-list-statistics'),
    path('global/policies/list/', GlobalPolicyListView.as_view(), name='global-policy-list'),
    path('global/policies/statistics/', GlobalPolicyStatisticsView.as_view(), name='global-policy-statistics'),
    path('global/policies/statistics/detail/', GlobalPolicyStatisticsDetailView.as_view(), name='global-policy-statistics-detail'),
    
    # Country Statistics
    path('countries/<int:country_id>/statistics/', CountryStatisticsDetailView.as_view(), name='country-statistics-detail'),
    path('countries/<int:country_id>/clients/statistics/', ClientStatisticsDetailView.as_view(), name='country-client-statistics'),
    path('countries/<int:country_id>/clients/list/', CountryClientStatisticsListView.as_view(), name='country-client-list'),
    path('countries/<int:country_id>/clients/<int:client_id>/statistics/', SpecificClientStatisticsDetailView.as_view(), name='country-client-statistics-detail'),
    path('countries/<int:country_id>/partners/statistics/', CountryPartnerStatisticsView.as_view(), name='country-partner-statistics'),
    path('countries/<int:country_id>/partners/list/', CountryPartnerListStatisticsView.as_view(), name='country-partner-list-statistics'),
    path('countries/<int:country_id>/insureds/statistics/', CountryInsuredStatisticsView.as_view(), name='country-insured-statistics'),
    path('countries/<int:country_id>/insureds/list/', CountryInsuredListStatisticsView.as_view(), name='country-insured-list-statistics'),
    path('countries/<int:country_id>/families/statistics/', CountryFamilyStatisticsView.as_view(), name='country-family-statistics'),
    path('countries/<int:country_id>/families/list/', CountryFamilyListView.as_view(), name='country-family-list'),
    path('countries/<int:country_id>/policies/statistics/', CountryPolicyStatisticsView.as_view(), name='country-policy-statistics'),    
    path('countries/<int:country_id>/policies/list/', CountryPolicyListView.as_view(), name='country-policy-list'),
    
    # Client Statistics
    path('clients/<int:client_id>/partners/statistics/', ClientPartnerStatisticsView.as_view(), name='client-partner-statistics'),
    path('clients/<int:client_id>/partners/list/', ClientPartnerListStatisticsView.as_view(), name='client-partner-list-statistics'),
    path('clients/<int:client_id>/families/statistics/', ClientFamilyStatisticsView.as_view(), name='client-family-statistics'),
    path('clients/<int:client_id>/families/list/', ClientFamilyListView.as_view(), name='client-family-list'),
    
    # Policy Statistics
    path('policies/<int:policy_id>/statistics/', SpecificPolicyStatisticsDetailView.as_view(), name='specific-policy-statistics-detail'),
    path('policies/<int:policy_id>/partners/statistics/', PolicyPartnerStatisticsView.as_view(), name='policy-partner-statistics'),
    path('policies/<int:policy_id>/partners/list/', PolicyPartnerListStatisticsView.as_view(), name='policy-partner-list-statistics'),
    
    # Partner Statistics
    path('partners/<int:partner_id>/statistics/', PartnerStatisticsView.as_view(), name='partner-statistics-detail'),
]
