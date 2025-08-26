from abc import ABC

from drf_spectacular.utils import extend_schema
from rest_framework.mixins import DestroyModelMixin

from app.pagination import StandardResultsSetPagination

from django.shortcuts import get_object_or_404

from rest_framework import filters, status
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet, ModelViewSet

from app.viewsets.utils import get_email_from_jwt


class BaseViewSet(ModelViewSet, ABC):
    lookup_value_regex = "[^/]+"  # This is to allow for special characters in the URL
    ordering_fields = "__all__"
    ordering = ["-orcabus_id"]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    http_method_names = ['get', 'post', 'patch', 'delete']

    def perform_destroy(self, instance):
        """
        The perform_destroy method is overridden to allow for the _history_user to be set.
        """
        requester_email = get_email_from_jwt(self.request)
        if not requester_email:
            raise ValueError("The requester email is not found in the JWT token.")

        instance._history_user = requester_email
        super().perform_destroy(instance)

    def perform_update(self, serializer):
        """
        The perform_destroy method is overridden to allow for the _history_user to be set.
        """
        requester_email = get_email_from_jwt(self.request)
        if not requester_email:
            raise ValueError("The requester email is not found in the JWT token.")

        serializer._history_user = requester_email
        super().perform_update(serializer)

    def perform_create(self, serializer):
        """
        The perform_create method is overridden to allow for the _history_user to be set.
        """
        requester_email = get_email_from_jwt(self.request)
        if not requester_email:
            raise ValueError("The requester email is not found in the JWT token.")

        serializer._history_user = requester_email
        super().perform_create(serializer)
