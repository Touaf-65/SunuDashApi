from rest_framework import serializers
from .models import File, ImportSession

class FileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    country = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = File
        fields = ['id', 'file', 'file_name', 'file_type', 'uploaded_at', 'size', 'user', 'country']
        read_only_fields = ['file_name', 'uploaded_at', 'size', 'user', 'country']

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

    class Meta:
        model = ImportSession
        fields = [
            'id', 'user', 'country', 'stat_file', 'recap_file', 'status',
            'created_at', 'started_at', 'completed_at', 'error_file', 'message',
        ]
        read_only_fields = ['status', 'created_at', 'started_at', 'completed_at', 'message', 'error_file']

