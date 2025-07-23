from rest_framework.permissions import BasePermission

class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser_role()

class IsGlobalAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin_global()

class IsTerritorialAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin_territorial()

class IsTerritorialAdminAndAssignedCountry(BasePermission):
    """
    Permission pour un admin territorial rattaché à un pays uniquement.
    Utile pour restreindre l'accès aux tableaux de bord liés à un pays.
    """
    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated and 
            user.role == user.Roles.ADMIN_TERRITORIAL and 
            user.country is not None
        )

class HasAccessCountry(BasePermission):
    """
    Autorise l'accès aux données seulement si :
    - superuser ou admin global (pas besoin de pays)
    - OU utilisateur (admin territorial, chef dept, opérateur) avec pays assigné
    """
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser_role() or user.is_admin_global():
            return True
        return user.country is not None

class IsChefDeptTech(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_chef_dept_tech()

class IsResponsableOperateur(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_responsable_operateur()
