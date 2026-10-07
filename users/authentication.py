from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

INACTIVE_COUNTRY_MESSAGE = (
    "Le pays auquel votre compte est rattaché est désactivé. "
    "Contactez un administrateur."
)

PASSWORD_CHANGE_REQUIRED_MESSAGE = (
    "Vous devez choisir un nouveau mot de passe avant de continuer."
)

# Routes encore accessibles à un compte qui doit changer son mot de passe
PASSWORD_CHANGE_ALLOWED_PREFIXES = (
    '/auth/change_password/',
    '/auth/getConnectedUser/',  # la page de connexion lit le profil juste après la connexion
)


class ActiveCountryJWTAuthentication(JWTAuthentication):
    """
    Authentification JWT par défaut de l'API (DEFAULT_AUTHENTICATION_CLASSES), qui ajoute :

    1. le gel des comptes rattachés à un pays désactivé (admin territorial, chef de
       département technique, responsable opérateur) : 401, code « country_inactive »,
       y compris pour un jeton obtenu avant la désactivation ;
    2. le changement de mot de passe obligatoire : un compte créé avec un mot de passe
       généré (must_change_password) n'a accès qu'au changement de mot de passe et à son
       profil ; tout le reste répond 403, code « password_change_required » (403 et non
       401 : la session reste ouverte, le frontend redirige vers le changement de mot de passe).
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user.has_inactive_country():
            # Même forme que les erreurs de jeton de simplejwt : {"detail": ..., "code": ...}
            raise AuthenticationFailed(
                {"detail": INACTIVE_COUNTRY_MESSAGE, "code": "country_inactive"},
                code="country_inactive",
            )
        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        if user.must_change_password and not request.path.startswith(PASSWORD_CHANGE_ALLOWED_PREFIXES):
            raise PermissionDenied(
                {"detail": PASSWORD_CHANGE_REQUIRED_MESSAGE, "code": "password_change_required"}
            )
        return user, token
