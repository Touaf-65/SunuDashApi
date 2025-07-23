from rest_framework import serializers
from .models import Country

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

    def validate_code(self, value):
        if not value.isalpha() or len(value) > 4:
            raise serializers.ValidationError("Le code pays doit contenir uniquement des lettres (max 4).")
        return value.upper()

    def validate_currency_code(self, value):
        if value and (not value.isalpha() or len(value) > 10):
            raise serializers.ValidationError("Code devise invalide.")
        return value.upper()

    def validate_currency_name(self, value):
        return value.strip().title() if value else value
