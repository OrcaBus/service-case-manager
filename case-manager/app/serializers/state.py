from rest_framework.serializers import ModelSerializer
from app.models import State
from app.serializers.utils import OrcabusIdSerializerMetaMixin
from rest_framework.fields import SerializerMethodField


class StateSerializer(ModelSerializer):
    created_by = SerializerMethodField()
    archived_by = SerializerMethodField()

    class Meta(OrcabusIdSerializerMetaMixin):
        model = State
        fields = "__all__"
        ordering = ["-timestamp"]
        read_only_fields = ["created_at", "created_by", "archived_at", "archived_by"]

    def get_created_by(self, obj) -> str | None:
        return obj.created_by.email if obj.created_by else None

    def get_archived_by(self, obj) -> str | None:
        return obj.archived_by.email if obj.archived_by else None


class StateDetailSerializer(ModelSerializer):
    from .comment import CommentSerializer

    comment = CommentSerializer(read_only=True)

    created_by = SerializerMethodField()
    archived_by = SerializerMethodField()

    class Meta(OrcabusIdSerializerMetaMixin):
        model = State
        fields = "__all__"
        read_only_fields = ["created_at", "created_by", "archived_at", "archived_by"]

    def get_created_by(self, obj) -> str | None:
        return obj.created_by.email if obj.created_by else None

    def get_archived_by(self, obj) -> str | None:
        return obj.archived_by.email if obj.archived_by else None
