from app.models import Comment
from app.serializers.comment import CommentSerializer

from .base import BaseViewSet


class CommentViewSet(BaseViewSet):
    serializer_class = CommentSerializer
    detail_serializer_class = CommentSerializer
    search_fields = Comment.get_base_fields()
    queryset = Comment.objects.all()


    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return Comment.objects.get_by_keyword(qs, **query_params)
