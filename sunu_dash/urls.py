from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("users.urls")),
    path("countries/", include("countries.urls")),
    path("data/", include("importer.urls")),
    path("files/", include("file_handling.file_urls")),
    path("import-sessions/", include("file_handling.importSession_urls")),
    path("dashboard/", include("dashboard.urls")),
    path("families/", include("core.family_urls")),
    path("settings/", include("core.settings_urls")),
    path("referential/", include("core.referential_urls")),
]

# MEDIA_ROOT (fichiers importés, journaux, rapports) n'est volontairement PAS servi par une route /media/ :
# ces fichiers ne sont accessibles que par les routes /files/ et /import-sessions/, qui contrôlent le pays et le rôle.
