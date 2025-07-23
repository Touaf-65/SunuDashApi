from django.urls import path
from .views import (CreateCountryView, CreateCountryFromExcel, ListCountriesView, 
    CountryDetailView, CountryUpdateView, CountryDeleteView, CountryReactivateView
)
urlpatterns = [
    path('create/', CreateCountryView.as_view(), name='create_country'),
    path('import_create/', CreateCountryFromExcel.as_view(), name='import_countries'),
    path('list/', ListCountriesView.as_view(), name='list_countries'),
    path('<int:pk>/', CountryDetailView.as_view(), name='country_detail'),
    path('<int:pk>/update/', CountryUpdateView.as_view(), name='country_detail'),
    path('<int:pk>/delete/', CountryDeleteView.as_view(), name='country_detail'),
    path('<int:pk>/restore/', CountryReactivateView.as_view(), name='restore_country')
]