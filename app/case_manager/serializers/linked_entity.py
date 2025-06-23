from case_manager.serializers.base import SerializersBase, OptionalFieldsMixin, OrcabusIdSerializerMetaMixin
from case_manager.models.linked_entity import LinkedEntity


class LinkedEntityBaseSerializer(SerializersBase):
    pass


class LinkedEntityListParamSerializer(OptionalFieldsMixin, LinkedEntityBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = LinkedEntity
        fields = "__all__"


class LinkedEntitySerializer(LinkedEntityBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = LinkedEntity
        fields = "__all__"
