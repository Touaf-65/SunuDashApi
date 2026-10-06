from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

INACTIVE_COUNTRY_MESSAGE = (
    "Le pays auquel votre compte est rattaché est désactivé. "
    "Contactez un administrateur."
)


class ActiveCountryJWTAuthentication(JWTAuthentication):
    """
    Authentification JWT qui gèle les comptes rattachés à un pays désactivé
    (admin territorial, chef de département technique, responsable opérateur).

    Appliquée à toutes les routes protégées via DEFAULT_AUTHENTICATION_CLASSES :
    un jeton encore valide obtenu avant la désactivation du pays est refusé (401),
    et l'accès revient dès que le pays est restauré.
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
