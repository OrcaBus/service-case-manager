from app.models import Case
from app.serializers import CaseDetailSerializer

from .base import BaseViewSet


class CaseViewSet(BaseViewSet):
    serializer_class = CaseDetailSerializer
    search_fields = Case.get_base_fields()
    queryset = Case.objects.prefetch_related('external_entity_set').all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return Case.objects.get_by_keyword(qs, **query_params)
