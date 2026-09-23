from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from app.models import ExternalEntity
from app.serializers import ExternalEntityDetailSerializer

from .base import BaseViewSet
from ..service.external_entity import resolve_pending_external_entities


class ExternalEntityViewSet(BaseViewSet):
    serializer_class = ExternalEntityDetailSerializer
    search_fields = ExternalEntity.get_base_fields()
    queryset = ExternalEntity.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return ExternalEntity.objects.get_by_keyword(qs, **query_params)

    @extend_schema(
        request=None,
        responses={
            "200": {
                "type": "object",
                "properties": {
                    "resolved": {"type": "integer"},
                    "still_pending": {"type": "integer"},
                    "skipped": {"type": "integer"},
                    "failed": {"type": "integer"},
                },
            }
        },
        description=(
            "Clean up pending external entities. Iterates every queued PendingExternalEntity "
            "of type 'sample': if the entity is no longer pending (a matching ExternalEntity now "
            "exists, or the metadata service can resolve it), it is linked to the pending entity's "
            "case and the pending row is deleted. Rows that cannot be resolved are left queued."
        ),
    )
    @action(detail=False, methods=["post"], url_path="cleanup-pending")
    def cleanup_pending(self, request, *args, **kwargs):

        result = resolve_pending_external_entities()
        return Response(result, status=status.HTTP_200_OK)
