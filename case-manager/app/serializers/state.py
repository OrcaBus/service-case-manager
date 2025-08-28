
from rest_framework.serializers import ModelSerializer
from app.models import State
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class StateSerializer(ModelSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = State
        fields = "__all__"

class StateDetailSerializer(ModelSerializer):
    from .case import CaseSerializer
    from .comment import CommentUserSerializer


    case = CaseSerializer(read_only=True)
    comment = CommentUserSerializer(read_only=True)

    class Meta(OrcabusIdSerializerMetaMixin):
        model = State
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]
