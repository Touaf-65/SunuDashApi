from django.urls import path
from importer.views import FileUploadAndImportView

urlpatterns = [
    path('upload/', FileUploadAndImportView.as_view(), name='file-upload-import'),
]
