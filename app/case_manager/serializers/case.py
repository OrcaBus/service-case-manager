from rest_framework import serializers

from case_manager.serializers.base import SerializersBase, OptionalFieldsMixin, OrcabusIdSerializerMetaMixin
from case_manager.models.case import Case
from case_manager.serializers.case_state import CaseStateMinSerializer


class CaseBaseSerializer(SerializersBase):
    # we only want to include the current state
    # all states are available via a dedicated endpoint
    current_state = serializers.SerializerMethodField()

    def get_current_state(self, obj) -> dict:
        latest_state = obj.get_latest_state()
        return CaseStateMinSerializer(latest_state).data if latest_state else None


class CaseListParamSerializer(OptionalFieldsMixin, CaseBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        fields = ["orcabus_id", "case_name", "description", "type",
                  "comment", ]


class CaseSerializer(CaseBaseSerializer):

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        exclude = ["libraries", "analysis_run"]


class CaseDetailSerializer(CaseBaseSerializer):
    current_state = serializers.SerializerMethodField()

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Case
        fields = "__all__"
