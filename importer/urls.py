from django.urls import path
from importer.views import FileUploadAndImportView #, UploadAndValidateFiles

urlpatterns = [
    path('upload/', FileUploadAndImportView.as_view(), name='file-upload-import'),
    # path('upload/', UploadAndValidateFiles.as_view(), name='file-upload-validate'),
]
