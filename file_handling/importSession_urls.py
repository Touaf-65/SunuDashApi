from django.urls import path
from  .views import ImportSessionListView, ImportSessionDownloadView, ImportSessionDeleteView

urlpatterns = [
    path('', ImportSessionListView.as_view(), name='import-session-list'),
    path('<int:pk>/delete/', ImportSessionDeleteView.as_view(), name='import-session-delete'),
    path('<int:pk>/download/', ImportSessionDownloadView.as_view(), name='import-session-download'),
]
