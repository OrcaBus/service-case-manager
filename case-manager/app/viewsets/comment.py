from rest_framework.mixins import UpdateModelMixin, CreateModelMixin

from app.models import Comment, User
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
        raise NotImplementedError()
