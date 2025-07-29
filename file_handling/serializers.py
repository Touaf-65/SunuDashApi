from rest_framework import serializers
from .models import File, ImportSession

class FileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    country = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = File
        fields = ['id', 'file', 'name', 'file_type', 'uploaded_at', 'size', 'user', 'country']
        read_only_fields = ['name', 'uploaded_at', 'size', 'user', 'country']

    def create(self, validated_data):
        # Assign user from context or request
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class ImportSessionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    country = serializers.StringRelatedField(read_only=True)
    stat_file = FileSerializer(read_only=True)
    recap_file = FileSerializer(read_only=True)

    error_file_url = serializers.SerializerMethodField()
    log_file_url = serializers.SerializerMethodField()


    class Meta:
        model = ImportSession
        fields = [
            'id', 'user', 'country', 'stat_file', 'recap_file', 'status',
            'created_at', 'started_at', 'completed_at', 'error_file', 'message',
            'error_file_url', 'log_file_url'
        ]
        read_only_fields = ['status', 'created_at', 'started_at', 'completed_at', 'message', 'error_file']

    def get_error_file_url(self, obj):
        request = self.context.get('request')
        if obj.error_file:
            return request.build_absolute_uri(f"/import-sessions/{obj.id}/download/?type=error")
        return None

    def get_log_file_url(self, obj):
        request = self.context.get('request')
        if obj.log_file_path:
            return request.build_absolute_uri(f"/import-sessions/{obj.id}/download/?type=log")
        return None
