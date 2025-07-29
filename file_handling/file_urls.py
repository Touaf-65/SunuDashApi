from django.urls import path
from  .views import FileListView, FileDeleteView, FileDownloadView, FilePreviewView

urlpatterns = [
    path('', FileListView.as_view(), name='file-list'),
    path('<int:pk>/delete/', FileDeleteView.as_view(), name='file-delete'),
    path('<int:pk>/download/', FileDownloadView.as_view(), name='file-download'),
    path('<int:pk>/preview/', FilePreviewView.as_view(), name='file-preview'),
]
