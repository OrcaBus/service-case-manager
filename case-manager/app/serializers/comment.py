from rest_framework.fields import CharField, SerializerMethodField
from rest_framework.serializers import ModelSerializer, ValidationError
from app.models import Comment
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class CommentSerializer(ModelSerializer):
    created_by = SerializerMethodField()
    archived_by = SerializerMethodField()

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Comment
        fields = "__all__"
        read_only_fields = ["created_at", "created_by", "archived_at", "archived_by"]

    def validate(self, attrs):
        """Comment must be attached to a case or state"""
        if not attrs.get("case") and not attrs.get("state"):
            raise ValidationError(
                "A comment must be associated with at least a 'case' or a 'state'."
            )
        return attrs

    def get_created_by(self, obj) -> str | None:
        return obj.created_by.email if obj.created_by else None

    def get_archived_by(self, obj) -> str | None:
        return obj.archived_by.email if obj.archived_by else None
