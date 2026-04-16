from rest_framework.mixins import UpdateModelMixin, CreateModelMixin

from app.models import Comment, User
from app.serializers.comment import CommentSerializer

from .base import BaseViewSet
from .utils import get_email_from_jwt


class CommentViewSet(BaseViewSet, CreateModelMixin, UpdateModelMixin):
    serializer_class = CommentSerializer
    detail_serializer_class = CommentSerializer
    search_fields = Comment.get_base_fields()
    queryset = Comment.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return Comment.objects.get_by_keyword(qs, **query_params)

    def _get_or_create_user_from_jwt(self):
        requester_email = get_email_from_jwt(self.request)
        user, _ = User.objects.get_or_create(email=requester_email)
        return user

    def perform_create(self, serializer):
        serializer.save(user=self._get_or_create_user_from_jwt())

    def perform_update(self, serializer):
        serializer.save(user=self._get_or_create_user_from_jwt())
