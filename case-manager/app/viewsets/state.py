from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response

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
        raise RuntimeError(
            "State records are immutable. To change a state, create a new one instead."
        )

    @extend_schema(
        responses={200: StateDetailSerializer},
        description="Archive a state record. Once archived, the state is marked immutable.",
    )
    @action(detail=True, methods=["patch"], url_path="archive", url_name="archive")
    def archive(self, request, *args, **kwargs):
        state = self.get_object()

        if state.is_archived:
            return Response(
                {"detail": "State is already archived."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        state.is_archived = True
        state.archived_at = timezone.now()
        state.archived_by = get_or_create_user_from_jwt(request)
        state.save()

        serializer = self.get_serializer(state)
        return Response(serializer.data, status=status.HTTP_200_OK)
