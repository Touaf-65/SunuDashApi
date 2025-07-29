from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("users.urls")),
    path("countries/", include("countries.urls")),
    path("data/", include("importer.urls")),
    path("files/", include("file_handling.file_urls")),
    path("import-sessions/", include("file_handling.importSession_urls")),
]

from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
