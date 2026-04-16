from rest_framework.fields import CharField
from rest_framework.serializers import ModelSerializer, ValidationError
from app.models import Comment
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class CommentSerializer(ModelSerializer):
    user = CharField(read_only=True)

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Comment
        fields = "__all__"

    def validate(self, attrs):
        """Comment must be attached to a case or state"""
        if not attrs.get("case") and not attrs.get("state"):
            raise ValidationError("A comment must be associated with at least a 'case' or a 'state'.")
        return attrs


class CommentUserSerializer(ModelSerializer):
    from .user import UserSerializer

    user = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = "__all__"
