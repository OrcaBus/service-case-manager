from drf_spectacular.utils import extend_schema_field
from rest_framework.fields import (
    ListField,
    SerializerMethodField,
    DateTimeField,
    DictField,
)
from rest_framework.serializers import (
    Serializer,
    ModelSerializer,
    CharField,
    EmailField,
)
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
        fields = ["timestamp", "external_entity"]


class CaseUserLinkSerializer(ModelSerializer):
    from .user import UserSerializer

    user = UserSerializer(read_only=True)

    class Meta:
        model = CaseUserLink
        fields = ["description", "timestamp", "user"]


class CaseDetailSerializer(ModelSerializer):
    from .state import StateSerializer
    from .comment import CommentSerializer

    alias = StringListField(required=False)
    external_entity_set = CaseExternalEntityLinkSerializer(
        source="caseexternalentitylink_set", many=True, read_only=True
    )
    user_set = CaseUserLinkSerializer(
        source="caseuserlink_set", many=True, read_only=True
    )
    latest_state = SerializerMethodField()
    comment_set = CommentSerializer(read_only=True, many=True)

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        fields = "__all__"

    @extend_schema_field(StateSerializer(allow_null=True))
    def get_latest_state(self, obj):
        from .state import StateSerializer

        state = obj.state_set.order_by("-event_at").first()
        if state:
            return StateSerializer(state).data
        return None


class CaseExternalEntityLinkCreateSerializer(ModelSerializer):
    case = CharField(read_only=True)
    external_entity = CharField()

    class Meta:
        model = CaseExternalEntityLink
        fields = "__all__"


class CaseUserCreateSerializer(ModelSerializer):
    case = CharField(read_only=True)
    email = EmailField(write_only=True)
    user = CharField(read_only=True)

    class Meta:
        model = CaseUserLink
        fields = "__all__"


class CaseHistorySerializer(CaseSerializer):
    class Meta:
        model = Case.history.model
        fields = "__all__"

    case = CharField(read_only=True)


class CaseTimelineSerializer(Serializer):
    """
    A unified read-only serializer for case timeline entries.
    Each entry describes one event, regardless of its source.
    """

    timestamp = DateTimeField()
    event_type = CharField()
    model_type = CharField()
    actor = CharField(allow_null=True)
    description = CharField()
    detail = DictField(allow_null=True)
