from drf_spectacular.utils import extend_schema

from case_manager.models.case import Case
from case_manager.serializers.case import CaseDetailSerializer, CaseSerializer, CaseListParamSerializer
from .base import BaseViewSet


class CaseViewSet(BaseViewSet):
    serializer_class = CaseDetailSerializer  # use detailed serializer as default
    search_fields = Case.get_base_fields()
    # queryset = Case.objects.prefetch_related("contexts").prefetch_related("workflows").all()

    @extend_schema(parameters=[
        CaseListParamSerializer
    ])
    def list(self, request, *args, **kwargs):
        self.serializer_class = CaseSerializer  # use simple serializer for list view
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        query_params = self.request.query_params.copy()
        return Case.objects.get_by_keyword(self.queryset, **query_params)
