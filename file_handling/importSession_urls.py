from django.urls import path
from  .views import ImportSessionListView, ImportSessionDownloadView, ImportSessionDeleteView
from importer.views import (
    ImportSessionSheetsView, ImportSessionAnalyseView, ImportSessionImportView, ImportSessionDetailView,
)

urlpatterns = [
    path('', ImportSessionListView.as_view(), name='import-session-list'),
    path('<int:pk>/', ImportSessionDetailView.as_view(), name='import-session-detail'),
    path('<int:pk>/delete/', ImportSessionDeleteView.as_view(), name='import-session-delete'),
    path('<int:pk>/download/', ImportSessionDownloadView.as_view(), name='import-session-download'),
    # Rapprochement (lots I1-I2) : feuilles du fichier statistique, rapprochement sur une feuille
    path('<int:pk>/sheets/', ImportSessionSheetsView.as_view(), name='import-session-sheets'),
    path('<int:pk>/analyse/', ImportSessionAnalyseView.as_view(), name='import-session-analyse'),
    # Écriture en base des sinistres importables (lot I3)
    path('<int:pk>/import/', ImportSessionImportView.as_view(), name='import-session-import'),
]
