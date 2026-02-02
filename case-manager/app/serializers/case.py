from rest_framework.fields import ListField
from rest_framework.serializers import ModelSerializer, CharField
from app.models import Case, CaseExternalEntityLink, CaseUserLink
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class StringListField(ListField):
    child = CharField()


class CaseSerializer(ModelSerializer):
    alias = StringListField(required=False)

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        exclude = ["user_set", "external_entity_set"]


class CaseExternalEntityLinkSerializer(ModelSerializer):
    from .external_entity import ExternalEntitySerializer

    external_entity = ExternalEntitySerializer(read_only=True)

    class Meta:
        model = CaseExternalEntityLink
        fields = ["timestamp", "added_via", "external_entity"]


class CaseUserLinkSerializer(ModelSerializer):
    from .user import UserSerializer

    user = UserSerializer(read_only=True)

    class Meta:
        model = CaseUserLink
        fields = ["description", "timestamp", "user"]


class CaseDetailSerializer(ModelSerializer):
    alias = StringListField(required=False)
    external_entity_set = CaseExternalEntityLinkSerializer(
        source="caseexternalentitylink_set", many=True, read_only=True
    )

    user_set = CaseUserLinkSerializer(
        source="caseuserlink_set", many=True, read_only=True
    )

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        fields = "__all__"


class CaseExternalEntityLinkCreateSerializer(ModelSerializer):
    case = CharField()
    external_entity = CharField()

    class Meta:
        model = CaseExternalEntityLink
        fields = "__all__"


class CaseUserCreateSerializer(ModelSerializer):
    class Meta:
        model = CaseUserLink
        fields = "__all__"
