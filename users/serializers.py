from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import CustomUser, PasswordResetToken
from .utils import validate_account_email, INVALID_EMAIL_MESSAGE
from countries.models import Country


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'code')  

class UserSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'country', 'role', 'is_active'
        )
        read_only_fields = ('username',)
        # Le contrôle de format de DRF passe avant validate_email : même message, en français
        extra_kwargs = {'email': {'error_messages': {'invalid': INVALID_EMAIL_MESSAGE}}}

    def validate_email(self, value):
        """Adresse ASCII uniquement (pas d'accent) et unique sans tenir compte de la casse."""
        try:
            value = validate_account_email(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages[0])
        duplicates = CustomUser.objects.filter(email__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Un utilisateur avec cet e-mail existe déjà.")
        return value

    def validate_role(self, value):
        """
        Un changement de rôle n'est accepté que si la vue l'autorise explicitement via
        context['assignable_roles'] ; par défaut, le rôle ne peut pas être modifié.
        Renvoyer le rôle actuel reste accepté (formulaires qui renvoient tous les champs).
        """
        current_role = self.instance.role if self.instance else None
        if value == current_role:
            return value
        if value not in self.context.get('assignable_roles', ()):
            raise serializers.ValidationError("Vous n'êtes pas autorisé à attribuer ce rôle.")
        return value

    def validate(self, data):
        if 'role' not in data:
            return data

        roles_requiring_country = [
            CustomUser.Roles.ADMIN_TERRITORIAL,
            CustomUser.Roles.CHEF_DEPT_TECH,
            CustomUser.Roles.RESP_OPERATEUR,
        ]
        # 'country' est en lecture seule : on vérifie le pays déjà enregistré du compte
        country = getattr(self.instance, 'country', None)

        if data['role'] in roles_requiring_country and not country:
            raise serializers.ValidationError({
                "country": "Ce champ est requis pour le rôle sélectionné."
            })

        return data

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value



class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    new_password = serializers.CharField(
        write_only=True, 
        min_length=8, 
        error_messages={
            'min_length': 'Le mot de passe doit contenir au moins 8 caractères.',
            'blank': 'Le mot de passe ne peut pas être vide.'
        }
    )
    confirm_password = serializers.CharField(
        write_only=True, 
        min_length=8,
        error_messages={
            'min_length': 'La confirmation du mot de passe doit contenir au moins 8 caractères.',
            'blank': 'La confirmation du mot de passe ne peut pas être vide.'
        }
    )

    def validate_token(self, value):
        if not PasswordResetToken.objects.filter(token=value, user__is_active=True).exists():
            raise serializers.ValidationError("Le lien de réinitialisation est invalide ou a expiré.")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': "Les mots de passe ne correspondent pas."
            })
        return attrs

