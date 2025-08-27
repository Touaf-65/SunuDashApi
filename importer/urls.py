from django.urls import path
from .views import FileUploadAndImportView

urlpatterns = [
    # URL pour l'import général
    path('upload/', FileUploadAndImportView.as_view(), name='file-upload-import'),
]
