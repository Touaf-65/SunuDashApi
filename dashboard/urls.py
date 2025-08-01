from django.urls import path
from .views import (CountryStatisticsDetailView, GlobalStatisticsDetailView, CountriesListStatisticsView
)

urlpatterns = [
    path('countries/<int:country_id>/statistics/', CountryStatisticsDetailView.as_view(), name='country-statistics-detail'), #ok
    path('global/statistics/', GlobalStatisticsDetailView.as_view(), name='global-statistics-detail'), 
    path('countries/statistics/', CountriesListStatisticsView.as_view(), name='countries-list-statistics-detail'),
]
