from rest_framework import serializers
from .models import File, ImportSession
from .access import can_delete, session_of_file


class FileSerializer(serializers.ModelSerializer):
    """Le chemin du fichier sur le serveur n'est jamais exposé : il se télécharge par l'API (download_url)."""
    user = serializers.StringRelatedField(read_only=True)
    country = serializers.StringRelatedField(read_only=True)
    download_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    import_session = serializers.SerializerMethodField()
    claims_count = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            'id', 'name', 'file_type', 'uploaded_at', 'size', 'user', 'country',
            'uploaded_by_name', 'uploaded_by_role',
            'download_url', 'preview_url', 'import_session', 'claims_count', 'can_delete',
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        return f"/files/{obj.id}/download/"

    def get_preview_url(self, obj):
        return f"/files/{obj.id}/preview/"

    def get_import_session(self, obj):
        session = session_of_file(obj)
        return session.id if session else None

    def get_claims_count(self, obj):
        """Sinistres écrits en base par l'import du fichier (proposés à la suppression avec lui)."""
        session = session_of_file(obj)
        return session.imported_claims.count() if session else 0

    def get_can_delete(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        session = session_of_file(obj)
        return can_delete(request.user, session or obj)


class ImportSessionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    country = serializers.StringRelatedField(read_only=True)
    stat_file = FileSerializer(read_only=True)
    recap_file = FileSerializer(read_only=True)

    recap_files_count = serializers.SerializerMethodField()
    claims_count = serializers.SerializerMethodField()
    error_file_url = serializers.SerializerMethodField()
    log_file_url = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = ImportSession
        fields = [
            'id', 'user', 'country', 'stat_file', 'recap_file', 'recap_files_count', 'stat_sheet', 'status',
            'step', 'progress', 'progress_label', 'progress_at',
            'created_at', 'started_at', 'completed_at', 'message', 'start_date', 'end_date', 'summary', 'currency',
            'claims_created_count', 'claims_count', 'insured_created_count', 'total_claimed_amount', 'total_reimbursed_amount',
            'uploaded_by_name', 'uploaded_by_role',
            'error_file_url', 'log_file_url', 'can_delete',
        ]
        read_only_fields = fields

    def get_claims_count(self, obj):
        return obj.imported_claims.count()

    def get_recap_files_count(self, obj):
        return obj.recap_files.count() or 1

    # Chemins relatifs à l'API (le frontend les préfixe par API_CONFIG.BASE_URL)
    def get_error_file_url(self, obj):
        return f"/import-sessions/{obj.id}/download/?type=error" if obj.error_file else None

    def get_log_file_url(self, obj):
        return f"/import-sessions/{obj.id}/download/?type=log" if obj.log_file_path else None

    def get_can_delete(self, obj):
        request = self.context.get('request')
        return bool(request) and can_delete(request.user, obj)
