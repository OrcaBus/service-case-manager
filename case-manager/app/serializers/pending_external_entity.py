from rest_framework.serializers import ModelSerializer

from app.models import PendingExternalEntity
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class PendingExternalEntitySerializer(ModelSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = PendingExternalEntity
        fields = ["orcabus_id", "alias", "type", "service_name"]
