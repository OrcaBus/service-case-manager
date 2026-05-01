import os
import boto3
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.mixins import DestroyModelMixin
from django.shortcuts import get_object_or_404
from rest_framework import status
from app.models import Case, CaseExternalEntityLink, State, User, CaseUserLink
from app.serializers import (
    CaseDetailSerializer,
    CaseExternalEntityLinkCreateSerializer,
    CaseUserCreateSerializer,
    CaseSerializer,
    StateSerializer,
)
from .base import BaseViewSetWithHistory
from .utils import get_email_from_jwt
from ..serializers.case import CaseHistorySerializer, CaseTimelineSerializer
from ..service.case import (
    link_case_to_external_entity_and_emit,
    unlink_case_to_external_entity_and_emit,
    get_case_activity,
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
            case, external_entity, get_email_from_jwt(request)
        )
        return Response(CaseExternalEntityLinkCreateSerializer(link).data)

    @extend_schema(
        responses={204: None},
        description="Removes a link between an external entity and a case.",
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path="external-entity/(?P<external_entity_orcabus_id>[^/]+)",
    )
    def unlink_external_entity(self, request, pk=None, external_entity_orcabus_id=None):
        link = get_object_or_404(
            CaseExternalEntityLink,
            case_id=pk,
            external_entity_id=external_entity_orcabus_id,
        )
        unlink_case_to_external_entity_and_emit(link, get_email_from_jwt(request))
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
        link = CaseUserLink(
            case=case,
            user=user,
            description=serializer.validated_data.get("description"),
        )
        requester_email = get_email_from_jwt(request)
        if requester_email:
            link._history_user = requester_email
        link.save()
        return Response(CaseUserCreateSerializer(link).data)

    @extend_schema(responses={204: None}, description="Unlinks a user from a case.")
    @action(
        detail=True,
        methods=["delete"],
        url_path="user/(?P<user_orcabus_id>[^/]+)",
    )
    def unlink_user(self, request, pk=None, user_orcabus_id=None):
        link = get_object_or_404(CaseUserLink, case_id=pk, user_id=user_orcabus_id)
        requester_email = get_email_from_jwt(request)
        if requester_email:
            link._history_user = requester_email
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

    @extend_schema(
        responses=StateSerializer(many=True),
        description="Retrieve all the states for a particular case",
    )
    @action(detail=True, methods=["get"], url_name="states", url_path="states")
    def retrieve_states(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")

        case_obj = get_object_or_404(self.queryset, pk=pk)
        state_obj_arr = State.objects.filter(case=case_obj).order_by("-event_at").all()

        page = self.paginate_queryset(state_obj_arr)
        serializer = StateSerializer(page, many=True)

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        responses=CaseTimelineSerializer(many=True),
        description="Retrieve the activity for the given case. This includes all changes to the case and its related "
        "models, such as states, comments, external entities, and linked users.",
    )
    @action(detail=True, methods=["get"], url_name="activity", url_path="activity")
    def retrieve_timeline(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")
        case_obj = get_object_or_404(self.queryset, pk=pk)
        entries = get_case_activity(case_obj)

        page = self.paginate_queryset(entries)
        serializer = CaseTimelineSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
