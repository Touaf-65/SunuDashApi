"""
Accès aux tableaux de bord et statistiques (lot D1, 10/10/2026).

Une seule règle pour toutes les routes de `dashboard/` :
- l'admin global voit tout (vues globales et n'importe quel pays) ;
- l'admin territorial et le chef de département technique ne voient que **leur pays** : le pays, l'employeur,
  la police ou le prestataire demandés dans l'URL doivent lui appartenir ;
- les vues globales (multi-pays) sont réservées à l'admin global (`global_only = True` sur la vue) ;
- le responsable opérateur n'accède qu'aux vues des opérateurs de saisie (`operator_view = True`), pour son pays
  (lot D4) ;
- les autres rôles (super-utilisateur…) n'ont pas accès aux statistiques.

Un objet d'un autre pays (ou inexistant) donne le même refus (403), pour ne pas révéler son existence. Les
combinaisons incohérentes de l'URL (employeur hors du pays indiqué, police non rattachée à l'employeur) donnent 404.
"""
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from core.models import Client, Insured, Operator, Partner, Policy

DENIED_MESSAGE = "Vous n'avez pas accès à ces statistiques."

# Paramètre d'URL -> modèle portant le pays
SCOPED_OBJECTS = {
    'client_id': Client,
    'policy_id': Policy,
    'partner_id': Partner,
    'insured_id': Insured,
    'operator_id': Operator,
}


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def check_url_consistency(kwargs):
    """404 si les identifiants de l'URL ne vont pas ensemble (vérifié pour tous les rôles)."""
    country_id = _as_int(kwargs.get('country_id'))
    client_id = _as_int(kwargs.get('client_id'))
    policy_id = _as_int(kwargs.get('policy_id'))
    if country_id and client_id and not Client.objects.filter(id=client_id, country_id=country_id).exists():
        raise NotFound("Cet employeur n'appartient pas à ce pays.")
    if client_id and policy_id and not Policy.objects.filter(id=policy_id, employers__id=client_id).exists():
        raise NotFound("Cette police n'est pas rattachée à cet employeur.")


def objects_in_country(kwargs, country_id):
    """True si tout ce que l'URL désigne (pays, employeur, police, prestataire) est dans `country_id`."""
    if 'country_id' in kwargs and _as_int(kwargs['country_id']) != country_id:
        return False
    for param, model in SCOPED_OBJECTS.items():
        if param in kwargs:
            object_id = _as_int(kwargs[param])
            if object_id is None or not model.objects.filter(id=object_id, country_id=country_id).exists():
                return False
    return True


class StatisticsAccess(BasePermission):
    """Permission commune aux vues de statistiques (voir l'en-tête du module)."""
    message = DENIED_MESSAGE

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        kwargs = getattr(view, 'kwargs', {}) or {}
        if user.is_admin_global():
            check_url_consistency(kwargs)
            return True
        if getattr(view, 'global_only', False):
            return False
        allowed = user.is_admin_territorial() or user.is_chef_dept_tech() or (
            getattr(view, 'operator_view', False) and user.is_responsable_operateur())
        if not allowed or not user.country_id:
            return False
        if not objects_in_country(kwargs, user.country_id):
            return False
        check_url_consistency(kwargs)
        return True
