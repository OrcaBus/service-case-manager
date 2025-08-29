from app.models import User
from app.serializers import UserDetailSerializer

from .base import BaseViewSet


class UserViewSet(BaseViewSet):
    serializer_class = UserDetailSerializer
    search_fields = User.get_base_fields()
    queryset = User.objects.all()

    def get_queryset(self):
        qs = self.queryset
        query_params = self.request.query_params.copy()

        return User.objects.get_by_keyword(qs, **query_params)
