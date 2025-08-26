from rest_framework.serializers import ModelSerializer
from app.models import User, CaseUserLink
from app.serializers.utils import OrcabusIdSerializerMetaMixin


class UserSerializer(ModelSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = User
        fields = "__all__"


class UserCaseSerializer(ModelSerializer):
    from .case import CaseSerializer

    case = CaseSerializer(read_only=True)

    class Meta:
        model = CaseUserLink
        fields = ['description', 'timestamp', 'case']


class UserDetailSerializer(ModelSerializer):
    case_set = UserCaseSerializer(source='caseuserlink_set', read_only=True, many=True)

    class Meta:
        model = User
        fields = "__all__"
