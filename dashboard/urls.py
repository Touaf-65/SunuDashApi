from django.urls import path
from .views import (
    # Global Statistics
    GlobalStatisticsDetailView, 
    GlobalCountriesListStatisticsView,
    GlobalClientStatisticsListView,
    GlobalPartnerStatisticsView,
    GlobalPartnerListStatisticsView,
    GlobalPolicyListView,
    
    # Country Statistics
    CountryStatisticsDetailView,
    CountryClientStatisticsDetailView,
    CountryClientStatisticsListView,
    CountryPartnerStatisticsView,
    CountryPartnerListStatisticsView,
    CountryInsuredStatisticsView,
    CountryInsuredListStatisticsView,
    CountryFamilyStatisticsView,
    
    # Territorial Statistics
    TerritorialPolicyListView,
    
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
    path('global/clients/list/', GlobalClientStatisticsListView.as_view(), name='global-client-list'),
    path('global/partners/statistics/', GlobalPartnerStatisticsView.as_view(), name='global-partner-statistics'),
    path('global/partners/list/', GlobalPartnerListStatisticsView.as_view(), name='global-partner-list-statistics'),
    path('global/policies/list/', GlobalPolicyListView.as_view(), name='global-policy-list'),
    
    # Country Statistics
    path('countries/<int:country_id>/statistics/', CountryStatisticsDetailView.as_view(), name='country-statistics-detail'),
    path('countries/<int:country_id>/clients/list/', CountryClientStatisticsListView.as_view(), name='country-client-list'),
    path('countries/<int:country_id>/clients/<int:client_id>/statistics/', CountryClientStatisticsDetailView.as_view(), name='country-client-statistics-detail'),
    path('countries/<int:country_id>/partners/statistics/', CountryPartnerStatisticsView.as_view(), name='country-partner-statistics'),
    path('countries/<int:country_id>/partners/list/', CountryPartnerListStatisticsView.as_view(), name='country-partner-list-statistics'),
    path('countries/<int:country_id>/insureds/statistics/', CountryInsuredStatisticsView.as_view(), name='country-insured-statistics'),
    path('countries/<int:country_id>/insureds/list/', CountryInsuredListStatisticsView.as_view(), name='country-insured-list-statistics'),
    path('countries/<int:country_id>/families/statistics/', CountryFamilyStatisticsView.as_view(), name='country-family-statistics'),
    
    # Territorial Statistics
    path('territorial/policies/list/', TerritorialPolicyListView.as_view(), name='territorial-policy-list'),
    
    # Client Statistics
    path('clients/<int:client_id>/partners/statistics/', ClientPartnerStatisticsView.as_view(), name='client-partner-statistics'),
    path('clients/<int:client_id>/partners/list/', ClientPartnerListStatisticsView.as_view(), name='client-partner-list-statistics'),
    
    # Policy Statistics
    path('policies/<int:policy_id>/partners/statistics/', PolicyPartnerStatisticsView.as_view(), name='policy-partner-statistics'),
    path('policies/<int:policy_id>/partners/list/', PolicyPartnerListStatisticsView.as_view(), name='policy-partner-list-statistics'),
    
    # Partner Statistics
    path('partners/<int:partner_id>/statistics/', PartnerStatisticsView.as_view(), name='partner-statistics-detail'),
]
