from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework import status
from app.models import (
    Case,
    CaseExternalEntityLink,
    State,
    User,
    CaseUserLink,
    ExternalSyncLog,
)
from app.serializers import (
    CaseDetailSerializer,
    CaseExternalEntityLinkCreateSerializer,
    CaseUserCreateSerializer,
    StateSerializer,
    ExternalSyncLogSerializer,
)
from .base import BaseViewSetWithHistory
from .utils import get_email_from_jwt
from ..serializers.case import CaseTimelineSerializer
from ..service.case import (
    link_case_to_external_entity_and_emit,
    unlink_case_to_external_entity_and_emit,
    get_case_activity,
)
from ..service.external_entity import get_or_create_external_entity
from ..service.redcap_import import (
    get_redcap_record_by_filter,
    upsert_case_from_redcap_record,
    upsert_redcap_records_by_date_range,
    auto_sync_redcap_records,
)


class RedcapDateRangeSyncSerializer(serializers.Serializer):
    after_date = serializers.DateField()
    before_date = serializers.DateField(required=False, allow_null=True, default=None)


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
        request=None,
        responses={
            "200": {
                "type": "object",
                "properties": {
                    "synced": {"type": "integer"},
                    "failed": {"type": "integer"},
                },
            }
        },
        description="Sync cases from REDCap from the last auto sync to the time this API is triggered.",
    )
    @action(detail=False, methods=["post"], url_path="sync-from-redcap/auto")
    def sync_from_redcap_auto(self, request, *args, **kwargs):

        result = auto_sync_redcap_records()
        return Response(result, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses=ExternalSyncLogSerializer(many=True),
        description="Get the REDCap auto sync history logs.",
    )
    @action(detail=False, methods=["get"], url_path="sync-from-redcap/auto/history")
    def sync_from_redcap_auto_history(self, request, *args, **kwargs):

        logs = ExternalSyncLog.objects.filter(external_service="redcap").order_by(
            "-imported_at"
        )
        page = self.paginate_queryset(logs)
        serializer = ExternalSyncLogSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=None,
        responses=CaseDetailSerializer,
        description="Sync a case from REDCap by its request form ID. Updates the case.",
    )
    @action(detail=True, methods=["post"], url_path="sync-from-redcap")
    def sync_case_from_redcap(self, request, *args, **kwargs):

        pk = self.kwargs.get("pk")
        case_obj = get_object_or_404(self.queryset, pk=pk)

        records = get_redcap_record_by_filter(
            filter_logic=f"[request_id]={case_obj.request_form_id}"
        )
        if not records:
            return Response(
                {
                    "detail": f"No REDCap record found for request_form_id '{case_obj.request_form_id}'."
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        case = upsert_case_from_redcap_record(records[0])
        return Response(CaseDetailSerializer(case).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=RedcapDateRangeSyncSerializer,
        responses={
            "200": {
                "type": "object",
                "properties": {
                    "synced": {"type": "integer"},
                    "failed": {"type": "integer"},
                },
            }
        },
        description="Sync cases from REDCap within a date range. Creates or updates matching cases.",
    )
    @action(detail=False, methods=["post"], url_path="sync-from-redcap")
    def sync_from_redcap_by_date_range(self, request, *args, **kwargs):
        serializer = RedcapDateRangeSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        after_date = serializer.validated_data["after_date"].isoformat()
        before_date = serializer.validated_data.get("before_date")
        if before_date:
            before_date = before_date.isoformat()

        result = upsert_redcap_records_by_date_range(
            after_date=after_date, before_date=before_date
        )
        return Response(result, status=status.HTTP_200_OK)

    @extend_schema(
        responses=StateSerializer(many=True),
        description="Retrieve all the states for a particular case.",
    )
    @action(detail=True, methods=["get"], url_name="states", url_path="states")
    def retrieve_states(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")

        case_obj = get_object_or_404(self.queryset, pk=pk)
        states = State.objects.filter(case=case_obj).order_by("-event_at").all()

        page = self.paginate_queryset(states)
        serializer = StateSerializer(page, many=True)

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        responses=CaseTimelineSerializer(many=True),
        description="Retrieve the activity for the given case. This includes all changes to the case and its related "
        "models, such as states, comments, external entities, and linked users.",
    )
    @action(detail=True, methods=["get"], url_name="activity", url_path="activity")
    def retrieve_activity(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")
        case_obj = get_object_or_404(self.queryset, pk=pk)
        entries = get_case_activity(case_obj)

        page = self.paginate_queryset(entries)
        serializer = CaseTimelineSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
