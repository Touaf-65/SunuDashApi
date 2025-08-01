from django.urls import path
from .views import CountryStatisticsDetailView 

urlpatterns = [
    path('countries/<int:country_id>/statistics/', CountryStatisticsDetailView.as_view(), name='country-statistics-detail'), #ok
    # Other URL patterns...
]
