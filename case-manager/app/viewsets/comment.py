from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response

from app.models import Comment
from app.serializers.comment import CommentSerializer

from .base import BaseViewSet
from .utils import get_or_create_user_from_jwt


class CommentViewSet(BaseViewSet, CreateModelMixin):
    serializer_class = CommentSerializer
    detail_serializer_class = CommentSerializer
    search_fields = Comment.get_base_fields()
    queryset = Comment.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return Comment.objects.get_by_keyword(qs, **query_params)

    def perform_create(self, serializer):
        serializer.save(created_by=get_or_create_user_from_jwt(self.request))

    def perform_update(self, serializer):
        raise RuntimeError(
            "Comments records are immutable. To change a comments, create a new one instead."
        )

    @extend_schema(
        responses={200: CommentSerializer},
        description="Archive a comment record. Once archived, the comment is marked immutable.",
    )
    @action(detail=True, methods=["patch"], url_path="archive", url_name="archive")
    def archive(self, request, *args, **kwargs):
        comment = self.get_object()

        if comment.is_archived:
            return Response(
                {"detail": "Comment is already archived."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment.is_archived = True
        comment.archived_at = timezone.now()
        comment.archived_by = get_or_create_user_from_jwt(request)
        comment.save()

        serializer = self.get_serializer(comment)
        return Response(serializer.data, status=status.HTTP_200_OK)
