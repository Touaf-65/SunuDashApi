from django.urls import path
from  .views import ImportSessionListView, ImportSessionDownloadView

urlpatterns = [
    path('', ImportSessionListView.as_view(), name='import-session-list'),
    path('<int:pk>/download/', ImportSessionDownloadView.as_view(), name='import-session-download'),
]
