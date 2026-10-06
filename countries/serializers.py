from rest_framework import serializers
from .models import Country


def clean_label(value):
    """
    Nettoie un libellé saisi (nom de pays, de devise) sans en changer la casse :
    espaces superflus retirés, première lettre en majuscule. Contrairement à
    str.title(), « Côte d'Ivoire » et « F CFA » restent intacts.
    """
    value = " ".join(value.split())
    return value[:1].upper() + value[1:]


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = (
            'id',
            'name',
            'code',
            'currency_code',
            'currency_name',
            'is_active',
        )
        # L'unicité du nom et du code est vérifiée dans validate_name / validate_code
        # (sans tenir compte de la casse, messages en français) : on retire les
        # validateurs d'unicité automatiques, sensibles à la casse et en anglais.
        extra_kwargs = {
            'name': {'validators': [], 'error_messages': {'blank': "Le nom du pays est requis."}},
            'code': {'validators': [], 'error_messages': {
                'blank': "Le code pays est requis.",
                'max_length': "Le code pays doit contenir uniquement des lettres (max 4).",
            }},
        }

    def validate_name(self, value):
        """
        Nom unique sans tenir compte de la casse (« togo » = « TOGO »). La contrainte
        unique de la base est sensible à la casse et ne suffit pas. Le pays modifié
        est exclu, pour pouvoir changer la casse de son propre nom.
        """
        value = clean_label(value)
        if not value:
            raise serializers.ValidationError("Le nom du pays est requis.")
        duplicates = Country.objects.filter(name__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(f"Un pays avec le nom « {value} » existe déjà.")
        return value

    def validate_code(self, value):
        if not value.isalpha() or len(value) > 4:
            raise serializers.ValidationError("Le code pays doit contenir uniquement des lettres (max 4).")
        value = value.upper()
        duplicates = Country.objects.filter(code__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(f"Un pays avec le code « {value} » existe déjà.")
        return value

    def validate_currency_code(self, value):
        if value and (not value.isalpha() or len(value) > 10):
            raise serializers.ValidationError("Code devise invalide.")
        return value.upper()

    def validate_currency_name(self, value):
        return clean_label(value) if value else value
