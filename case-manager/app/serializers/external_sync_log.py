from rest_framework.serializers import ModelSerializer

from app.models import ExternalSyncLog


class ExternalSyncLogSerializer(ModelSerializer):
    class Meta:
        model = ExternalSyncLog
        fields = "__all__"
