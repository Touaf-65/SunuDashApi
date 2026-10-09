"""
Règles d'accès aux fichiers importés et aux sessions d'import (décidées le 08/10/2026).

- Seuls l'admin territorial (AT) et le chef de département technique (CDT) **du pays** du fichier y ont accès :
  liste, téléchargement, aperçu, journaux. Pour tout autre compte, le fichier « n'existe pas » (404).
- Suppression (toujours la session entière) :
    * importé par un AT  -> cet AT seulement ; si l'auteur n'est plus AT de ce pays (réaffecté, désactivé,
      supprimé, changé de rôle), les AT actuels du pays peuvent supprimer ;
    * importé par un CDT -> ce CDT et les AT du pays.
"""
import os

from django.conf import settings
from rest_framework.permissions import BasePermission

from users.models import CustomUser as User
from .models import File, ImportSession

FILE_ROLES = (User.Roles.ADMIN_TERRITORIAL, User.Roles.CHEF_DEPT_TECH)

ALLOWED_EXTENSIONS = ('.xlsx', '.xls', '.csv')

DELETE_FORBIDDEN_MESSAGE = (
    "Vous ne pouvez pas supprimer cet import : seul son auteur peut le faire "
    "(ou l'admin territorial pour un import du chef de département technique)."
)


class CanAccessCountryFiles(BasePermission):
    """AT ou CDT rattaché à un pays."""
    message = "Seuls l'admin territorial et le chef de département technique d'un pays ont accès à ses fichiers."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and user.role in FILE_ROLES
            and user.country_id is not None
        )


MAX_UPLOAD_SIZE = getattr(settings, 'IMPORT_FILE_MAX_SIZE', 50 * 1024 * 1024)

# Signature des premiers octets selon l'extension (un .xlsx renommé en .csv, ou un exécutable renommé, est refusé)
_XLSX_MAGIC = b'PK\x03\x04'
_XLS_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def validate_uploaded_file(uploaded, label):
    """Renvoie un message d'erreur en français, ou None si le fichier est acceptable."""
    name = (uploaded.name or '').lower()
    ext = os.path.splitext(name)[1]
    if ext not in ALLOWED_EXTENSIONS:
        return f"{label} : format non accepté. Formats acceptés : .xlsx, .xls, .csv."
    if uploaded.size == 0:
        return f"{label} : le fichier est vide."
    if uploaded.size > MAX_UPLOAD_SIZE:
        return f"{label} : fichier trop volumineux (maximum {MAX_UPLOAD_SIZE // (1024 * 1024)} Mo)."

    head = uploaded.read(2048)
    uploaded.seek(0)
    if ext == '.xlsx' and not head.startswith(_XLSX_MAGIC):
        return f"{label} : le contenu n'est pas un classeur Excel .xlsx valide."
    if ext == '.xls' and not head.startswith(_XLS_MAGIC):
        return f"{label} : le contenu n'est pas un classeur Excel .xls valide."
    if ext == '.csv' and (b'\x00' in head or head.startswith(_XLSX_MAGIC) or head.startswith(_XLS_MAGIC)):
        return f"{label} : le contenu n'est pas un fichier texte CSV."
    return None


def files_for(user):
    return File.objects.filter(country_id=user.country_id)


def sessions_for(user):
    return ImportSession.objects.filter(country_id=user.country_id)


def session_of_file(file):
    """Session d'import à laquelle appartient le fichier (stat ou l'un des récaps), ou None."""
    return (
        ImportSession.objects.filter(stat_file=file).first()
        or ImportSession.objects.filter(recap_file=file).first()
        or ImportSession.objects.filter(recap_files=file).first()
    )


def session_files(session):
    """Tous les fichiers d'une session : statistique et récaps."""
    ids = {session.stat_file_id, session.recap_file_id}
    ids.update(session.recap_files.values_list('pk', flat=True))
    return File.objects.filter(pk__in=ids)


def _is_territorial_admin_of(user, country_id):
    return (
        user is not None
        and user.is_active
        and user.role == User.Roles.ADMIN_TERRITORIAL
        and user.country_id == country_id
    )


def can_delete(user, obj):
    """`obj` : ImportSession ou File (fichier hors session). L'appelant a déjà vérifié le pays."""
    if user.country_id != obj.country_id or user.role not in FILE_ROLES:
        return False

    author = obj.user
    is_author = author is not None and author.pk == user.pk
    user_is_at = user.role == User.Roles.ADMIN_TERRITORIAL

    if obj.uploaded_by_role == User.Roles.CHEF_DEPT_TECH:
        return is_author or user_is_at

    # Importé par un AT (ou rôle inconnu pour un ancien import) : l'auteur, ou un AT actuel si l'auteur
    # n'est plus AT de ce pays
    if is_author:
        return True
    return user_is_at and not _is_territorial_admin_of(author, obj.country_id)


def file_paths(*fields):
    """Chemins sur disque des FileField renseignés."""
    paths = []
    for field in fields:
        if field and field.name:
            try:
                paths.append(field.path)
            except (ValueError, NotImplementedError):
                pass
    return paths


def stored_paths(session):
    """Chemins sur disque des fichiers d'une session (à effacer après suppression)."""
    paths = file_paths(*(f.file for f in session_files(session)), session.error_file)
    if session.log_file_path:
        log_path = os.path.abspath(session.log_file_path)
        # On n'efface un journal que s'il est sous MEDIA_ROOT
        if log_path.startswith(os.path.abspath(settings.MEDIA_ROOT) + os.sep):
            paths.append(log_path)
    return paths


def remove_paths(paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass
