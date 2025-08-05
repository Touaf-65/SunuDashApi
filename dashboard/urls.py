from django.urls import path
from .views import (CountryStatisticsDetailView, GlobalStatisticsDetailView, CountriesListStatisticsView, ClientStatisticView, GlobalClientStatisticListView,
 ClientStatisticListView, ClientPolicyStatisticsView, ClientPolicyListStatisticsView, PartnerStatisticsView, PartnerListStatisticsView,
 CountryPartnerStatisticsView, CountryPartnerListStatisticsView, ClientPartnerStatisticsView, ClientPartnerListStatisticsView,
 PolicyPartnerStatisticsView, PolicyPartnerListStatisticsView, PartnerStatisticsView, CountryInsuredStatisticsView, CountryInsuredListStatisticsView,
 CountryFamilyStatisticsView
)

urlpatterns = [
    path('countries/<int:country_id>/statistics/', CountryStatisticsDetailView.as_view(), name='country-statistics-detail'), #ok
    path('global/statistics/', GlobalStatisticsDetailView.as_view(), name='global-statistics-detail'), 
    path('countries/statistics/', CountriesListStatisticsView.as_view(), name='countries-list-statistics-detail'),
    path('clients/<int:client_id>/statistics/', ClientStatisticView.as_view(), name='client-statistics-detail'),
    path('global/clients/statistics/', GlobalClientStatisticListView.as_view(), name='global-client-statistics-list-detail'),
    path('clients/statistics/', ClientStatisticListView.as_view(), name='client-statistics-list-detail'),
    path('clients/policies/<int:policy_id>/statistics/', ClientPolicyStatisticsView.as_view(), name='client-policy-statistics-detail'),
    path('clients/policies/statistics/', ClientPolicyListStatisticsView.as_view(), name='client-policy-list-statistics-detail'),
    path('partners/statistics/', PartnerStatisticsView.as_view(), name='partner-statistics-detail'),
    path('partners/list/', PartnerListStatisticsView.as_view(), name='partner-list-statistics-detail'),
    path('countries/<int:country_id>/partners/statistics/', CountryPartnerStatisticsView.as_view(), name='country-partner-statistics-detail'),
    path('countries/<int:country_id>/partners/list/', CountryPartnerListStatisticsView.as_view(), name='country-partner-list-statistics-detail'),
    path('clients/<int:client_id>/partners/statistics/', ClientPartnerStatisticsView.as_view(), name='client-partner-statistics-detail'),
    path('clients/<int:client_id>/partners/list/', ClientPartnerListStatisticsView.as_view(), name='client-partner-list-statistics-detail'),
    path('clients/policies/<int:policy_id>/partners/statistics/', PolicyPartnerStatisticsView.as_view(), name='policy-partner-statistics-detail'),
    path('clients/policies/<int:policy_id>/partners/list/', PolicyPartnerListStatisticsView.as_view(), name='policy-partner-list-statistics-detail'),
    path('partners/<int:partner_id>/statistics/', PartnerStatisticsView.as_view(), name='partner-statistics-detail'),
    path('countries/insureds/statistics/', CountryInsuredStatisticsView.as_view(), name='country-insured-statistics-detail'),
    path('countries/insureds/list/', CountryInsuredListStatisticsView.as_view(), name='country-insured-list-statistics-detail'),
    path('countries/families/statistics/', CountryFamilyStatisticsView.as_view(), name='country-family-statistics-detail'),
]
