
from app.models import ExternalEntity
from app.serializers import ExternalEntityDetailSerializer

from .base import BaseViewSet


class ExternalEntityViewSet(BaseViewSet):
    serializer_class = ExternalEntityDetailSerializer
    search_fields = ExternalEntity.get_base_fields()
    queryset = ExternalEntity.objects.all()


    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return ExternalEntity.objects.get_by_keyword(qs, **query_params)
