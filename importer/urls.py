from django.urls import path
from .views.prime_import_views import (
    PrimeImportPreviewView,
    PrimeImportView,
    PrimeImportStatusView,
    ClientPrimeListView,
    ClientPrimeHistoryView
)

urlpatterns = [
    # URLs existantes pour l'import général
    # ... (ajoutez ici les URLs existantes si elles existent)
    
    # URLs pour l'import des primes
    path('prime-import/preview/', PrimeImportPreviewView.as_view(), name='prime-import-preview'),
    path('prime-import/', PrimeImportView.as_view(), name='prime-import'),
    path('prime-import/status/<int:import_session_id>/', PrimeImportStatusView.as_view(), name='prime-import-status'),
    path('prime-import/clients/', ClientPrimeListView.as_view(), name='client-prime-list'),
    path('prime-import/clients/<int:client_id>/history/', ClientPrimeHistoryView.as_view(), name='client-prime-history'),
]
