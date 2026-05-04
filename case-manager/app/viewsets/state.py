from rest_framework.mixins import CreateModelMixin

from app.models import State
from app.serializers import StateDetailSerializer

from .base import BaseViewSet
from .utils import get_or_create_user_from_jwt


class StateViewSet(BaseViewSet, CreateModelMixin):
    serializer_class = StateDetailSerializer
    search_fields = State.get_base_fields()
    queryset = State.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return State.objects.get_by_keyword(qs, **query_params)

    def perform_create(self, serializer):
        serializer.save(created_by=get_or_create_user_from_jwt(self.request))

    def perform_update(self, serializer):
        raise NotImplementedError()
