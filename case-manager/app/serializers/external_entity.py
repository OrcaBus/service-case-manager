from rest_framework.serializers import ModelSerializer
from app.models import ExternalEntity, CaseExternalEntityLink
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class ExternalEntitySerializer(ModelSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = ExternalEntity
        fields = "__all__"


class ExternalEntityCaseLinkSerializer(ModelSerializer):
    from .case import CaseSerializer

    case = CaseSerializer(read_only=True)

    class Meta:
        model = CaseExternalEntityLink
        fields = ['timestamp', 'added_via', 'case']


class ExternalEntityDetailSerializer(ModelSerializer):
    case = ExternalEntityCaseLinkSerializer(source='caseexternalentitylink_set', many=True, read_only=True)

    class Meta:
        model = ExternalEntity
        fields = '__all__'
