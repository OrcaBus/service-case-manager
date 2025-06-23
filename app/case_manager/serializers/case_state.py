from case_manager.serializers.base import SerializersBase, OrcabusIdSerializerMetaMixin
from case_manager.models.case import Case
from case_manager.models.case_state import CaseState


class CaseStateBaseSerializer(SerializersBase):
    pass


class CaseStateMinSerializer(CaseStateBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = CaseState
        fields = ["orcabus_id", "status", "timestamp"]


class CaseStateSerializer(CaseStateBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        fields = "__all__"
