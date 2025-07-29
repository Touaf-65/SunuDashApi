from rest_framework import serializers
from .models import CustomUser, PasswordResetToken
from countries.models import Country


class UserSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CustomUser
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'country', 'role', 'is_active'
        )
        read_only_fields = ('username',)

    def validate(self, data):
        role = data.get('role', None)
        country = data.get('country', None)

        roles_requiring_country = [
            CustomUser.Roles.ADMIN_TERRITORIAL,
            CustomUser.Roles.CHEF_DEPT_TECH,
            CustomUser.Roles.RESP_OPERATEUR,
        ]

        if role in roles_requiring_country and not country:
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

