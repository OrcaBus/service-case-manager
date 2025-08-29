from app.models import State
from app.serializers import StateDetailSerializer

from .base import BaseViewSet


class StateViewSet(BaseViewSet):
    serializer_class = StateDetailSerializer
    search_fields = State.get_base_fields()
    queryset = State.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return State.objects.get_by_keyword(qs, **query_params)
