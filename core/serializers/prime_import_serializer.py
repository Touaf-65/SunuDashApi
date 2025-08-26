"""
Serializers pour l'import des primes clients
"""

from rest_framework import serializers
from file_handling.models import File, ImportSession
from core.models import Client, ClientPrimeHistory


class PrimeImportPreviewSerializer(serializers.Serializer):
    """
    Serializer pour l'aperçu de l'import des primes
    """
    total_rows = serializers.IntegerField()
    valid_rows = serializers.IntegerField()
    invalid_rows = serializers.IntegerField()
    clients_not_found = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
    duplicate_names = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    sample_data = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
    sample_errors = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )


class PrimeImportResultSerializer(serializers.Serializer):
    """
    Serializer pour les résultats de l'import des primes
    """
    imported_count = serializers.IntegerField()
    total_valid = serializers.IntegerField()
    total_invalid = serializers.IntegerField()
    clients_not_found = serializers.IntegerField()
    duplicate_names = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    errors = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
    import_session_id = serializers.IntegerField()


class PrimeImportRequestSerializer(serializers.Serializer):
    """
    Serializer pour la requête d'import des primes
    """
    file = serializers.FileField(
        help_text="Fichier Excel contenant les primes clients"
    )
    
    def validate_file(self, value):
        """
        Valide le fichier uploadé
        """
        # Vérifier l'extension
        if not value.name.endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError(
                "Le fichier doit être au format Excel (.xlsx ou .xls)"
            )
        
        # Vérifier la taille (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(
                "Le fichier ne peut pas dépasser 10MB"
            )
        
        return value


class ClientPrimeHistorySerializer(serializers.ModelSerializer):
    """
    Serializer pour l'historique des primes client
    """
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_country = serializers.CharField(source='client.country.name', read_only=True)
    
    class Meta:
        model = ClientPrimeHistory
        fields = [
            'id', 'client', 'client_name', 'client_country',
            'prime', 'date'
        ]
        read_only_fields = ['id', 'date']


class ClientPrimeSerializer(serializers.ModelSerializer):
    """
    Serializer pour les primes client avec historique
    """
    prime_history = ClientPrimeHistorySerializer(
        source='prime_history',
        many=True,
        read_only=True
    )
    country_name = serializers.CharField(source='country.name', read_only=True)
    
    class Meta:
        model = Client
        fields = [
            'id', 'name', 'country', 'country_name',
            'prime', 'prime_history', 'creation_date', 'modification_date'
        ]
        read_only_fields = ['id', 'creation_date', 'modification_date']


class PrimeValidationErrorSerializer(serializers.Serializer):
    """
    Serializer pour les erreurs de validation des primes
    """
    client_name = serializers.CharField()
    row_number = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.CharField())


class PrimeImportStatusSerializer(serializers.Serializer):
    """
    Serializer pour le statut d'import des primes
    """
    import_session_id = serializers.IntegerField()
    status = serializers.CharField()
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(required=False)
    progress = serializers.IntegerField(required=False)
    message = serializers.CharField(required=False)

