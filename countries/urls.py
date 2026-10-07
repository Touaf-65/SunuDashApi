from django.urls import path
from .views import (CreateCountryView, CreateCountryFromExcel, ListCountriesView,
    CountryDetailView, CountryUpdateView, CountryDeactivateView, CountryReactivateView,
    DeactivationRequestListView, DeactivationRequestActionView,
)
urlpatterns = [
    path('create/', CreateCountryView.as_view(), name='create_country'),
    path('import_create/', CreateCountryFromExcel.as_view(), name='import_countries'),
    path('list/', ListCountriesView.as_view(), name='list_countries'),
    path('<int:pk>/', CountryDetailView.as_view(), name='country_detail'),
    path('<int:pk>/update/', CountryUpdateView.as_view(), name='country_update'),
    # Pas de suppression : un pays se désactive (demande + quorum, ou SUPERUSER)
    path('<int:pk>/deactivate/', CountryDeactivateView.as_view(), name='country_deactivate'),
    path('<int:pk>/restore/', CountryReactivateView.as_view(), name='restore_country'),
    path('deactivation-requests/', DeactivationRequestListView.as_view(), name='deactivation_requests'),
    path('deactivation-requests/<int:pk>/approve/',
         DeactivationRequestActionView.as_view(action='approve'), name='deactivation_request_approve'),
    path('deactivation-requests/<int:pk>/reject/',
         DeactivationRequestActionView.as_view(action='reject'), name='deactivation_request_reject'),
    path('deactivation-requests/<int:pk>/cancel/',
         DeactivationRequestActionView.as_view(action='cancel'), name='deactivation_request_cancel'),
]
