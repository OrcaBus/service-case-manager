from rest_framework.serializers import ModelSerializer
from app.models import Comment
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class CommentSerializer(ModelSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = Comment
        fields = "__all__"

class CommentUserSerializer(ModelSerializer):
    from .user import UserSerializer

    user = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields =  "__all__"
