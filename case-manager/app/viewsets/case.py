import os
import boto3
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.mixins import DestroyModelMixin
from django.shortcuts import get_object_or_404
from rest_framework import status
from app.models import Case, CaseExternalEntityLink, ExternalEntity, User, CaseUserLink
from app.serializers import (
    CaseDetailSerializer,
    CaseExternalEntityLinkCreateSerializer,
    CaseUserCreateSerializer, CaseSerializer,
)
from .base import BaseViewSetWithHistory
from ..serializers.case import CaseHistorySerializer
from ..service.case import (
    link_case_to_external_entity_and_emit,
    unlink_case_to_external_entity_and_emit,
)
from ..service.external_entity import get_or_create_external_entity


class CaseLinkMixin:

    @extend_schema(
        request=CaseExternalEntityLinkCreateSerializer,
        responses=CaseExternalEntityLinkCreateSerializer,
        description="Links an external entity to a case.",
    )
    @action(detail=True, methods=["post"], url_path="external-entity")
    def link_external_entity(self, request, pk=None, *args, **kwargs):
        serializer = CaseExternalEntityLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = get_object_or_404(Case, pk=pk)
        external_entity = get_or_create_external_entity(
            serializer.validated_data["external_entity"]
        )
        link = link_case_to_external_entity_and_emit(
            case, external_entity, added_via=serializer.validated_data.get("added_via")
        )
        return Response(CaseExternalEntityLinkCreateSerializer(link).data)

    @extend_schema(responses={204: None}, description="Removes a link between an external entity and a case.")
    @action(
        detail=True, methods=["delete"],
        url_path="external-entity/(?P<external_entity_orcabus_id>[^/]+)",
    )
    def unlink_external_entity(self, request, pk=None, external_entity_orcabus_id=None):
        link = get_object_or_404(
            CaseExternalEntityLink,
            case_id=pk,
            external_entity_id=external_entity_orcabus_id,
        )
        unlink_case_to_external_entity_and_emit(link)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=CaseUserCreateSerializer,
        responses=CaseUserCreateSerializer,
        description="Links a user to a case.",
    )
    @action(detail=True, methods=["post"], url_path="user")
    def link_user(self, request, pk=None, *args, **kwargs):
        serializer = CaseUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = get_object_or_404(Case, pk=pk)
        user, _ = User.objects.get_or_create(email=serializer.validated_data["email"])
        link = CaseUserLink.objects.create(
            case=case, user=user,
            description=serializer.validated_data.get("description"),
        )
        return Response(CaseUserCreateSerializer(link).data)

    @extend_schema(responses={204: None}, description="Unlinks a user from a case.")
    @action(
        detail=True, methods=["delete"],
        url_path="user/(?P<user_orcabus_id>[^/]+)",
    )
    def unlink_user(self, request, pk=None, user_orcabus_id=None):
        link = get_object_or_404(CaseUserLink, case_id=pk, user_id=user_orcabus_id)
        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CaseViewSet(BaseViewSetWithHistory, CaseLinkMixin):
    serializer_class = CaseDetailSerializer
    search_fields = Case.get_base_fields()
    queryset = Case.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return Case.objects.get_by_keyword(qs, **query_params)

    @extend_schema(responses=CaseHistorySerializer(many=True), description="Retrieve the history of this model")
    @action(detail=True, methods=['get'], url_name='history', url_path='history')
    def retrieve_history(self, request, *args, **kwargs):
        return super().retrieve_history(CaseHistorySerializer)

    @extend_schema(
        request=None,
        responses={202: {"description": "Case generation process started"}},
        description="Automatically generate new cases based on existing library and runs.",
    )
    @action(detail=False, methods=["post"], url_name="generate", url_path="generate")
    def generate(self, request):
        lambda_arn = os.environ["CASE_FINDER_LAMBDA_ARN"]
        client = boto3.client("lambda", region_name="ap-southeast-2")

        client.invoke(
            FunctionName=lambda_arn,
            InvocationType="Event",
        )

        return Response(
            {"message": "Case generation process has been started."},
            status=status.HTTP_202_ACCEPTED,
        )
