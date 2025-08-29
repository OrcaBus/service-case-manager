from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework import status
from app.models import Case, CaseExternalEntityLink, ExternalEntity, User, CaseUserLink
from app.serializers import (
    CaseDetailSerializer,
    CaseExternalEntityLinkCreateSerializer,
    CaseUserCreateSerializer,
)
from .base import BaseViewSet


class CaseViewSet(BaseViewSet):
    serializer_class = CaseDetailSerializer
    search_fields = Case.get_base_fields()
    queryset = Case.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return Case.objects.get_by_keyword(qs, **query_params)

    @extend_schema(
        request=CaseExternalEntityLinkCreateSerializer,
        responses=CaseExternalEntityLinkCreateSerializer,
        description="Links an external entity to a case.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_name="link/external-entity",
        url_path="link/external-entity",
    )
    def create_case_external_entity_relationship(self, request, *args, **kwargs):
        serializer = CaseExternalEntityLinkCreateSerializer(
            data=request.data, many=False
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.data
        case_orcabus_id = data.get("case", None)
        external_entity_orcabus_id = data.get("external_entity", None)

        case = get_object_or_404(Case, pk=case_orcabus_id)
        external_entity = get_object_or_404(
            ExternalEntity, pk=external_entity_orcabus_id
        )

        case_entity_link = CaseExternalEntityLink.objects.create(
            case=case,
            external_entity=external_entity,
            added_via=data.get("added_via", None),
        )
        res_data = CaseExternalEntityLinkCreateSerializer(case_entity_link).data

        return Response(res_data)

    @extend_schema(
        responses={204: None},
        description="Remove a link between external entity and the case.",
    )
    @action(
        detail=True,
        methods=["delete"],
        url_name="remove_case_external_entity_relationship",
        url_path="external-entity/(?P<external_entity_orcabus_id>[^/]+)",
    )
    def unlink_case_external_entity(self, request, *args, **kwargs):
        case_orcabus_id = kwargs.get("pk", None)
        external_entity_orcabus_id = kwargs.get("external_entity_orcabus_id", None)

        link = get_object_or_404(
            CaseExternalEntityLink,
            case_id=case_orcabus_id,
            external_entity_id=external_entity_orcabus_id,
        )
        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=CaseUserCreateSerializer,
        responses=CaseUserCreateSerializer,
        description="Links a user to a case.",
    )
    @action(detail=False, methods=["post"], url_name="link/user", url_path="link/user")
    def create_case_user_relationship(self, request, *args, **kwargs):
        serializer = CaseUserCreateSerializer(data=request.data, many=False)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.data
        case_orcabus_id = data.get("case", None)
        user_orcabus_id = data.get("user", None)

        case = get_object_or_404(Case, pk=case_orcabus_id)
        user = get_object_or_404(User, pk=user_orcabus_id)

        case_user_link = CaseUserLink.objects.create(
            case=case, user=user, description=data.get("description", None)
        )
        res_data = CaseUserCreateSerializer(case_user_link).data

        return Response(res_data)

    @extend_schema(responses={204: None}, description="Unlinks a user from a case.")
    @action(
        detail=True,
        methods=["delete"],
        url_name="remove_case_user_relationship",
        url_path="user/(?P<user_orcabus_id>[^/]+)",
    )
    def unlink_case_user(self, request, *args, **kwargs):
        case_orcabus_id = kwargs.get("pk", None)
        user_orcabus_id = kwargs.get("user_orcabus_id", None)

        link = get_object_or_404(
            CaseUserLink, case_id=case_orcabus_id, user_id=user_orcabus_id
        )
        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
