from django.urls import path, include
from django.urls import path
from drf_spectacular.views import SpectacularJSONAPIView, SpectacularSwaggerView

from app.routers import OptionalSlashDefaultRouter

from app.settings.base import API_VERSION
from app.viewsets import CaseViewSet, CommentViewSet, ExternalEntityViewSet, StateViewSet, UserViewSet

api_namespace = "api"
api_version = API_VERSION
api_base = f"{api_namespace}/{api_version}/"

router = OptionalSlashDefaultRouter()
router.register(r"case", CaseViewSet, basename="case")
router.register(r"comment", CommentViewSet, basename="comment")
router.register(r"external-entity", ExternalEntityViewSet, basename="external-entity")
router.register(r"state", StateViewSet, basename="state")
router.register(r"user", UserViewSet, basename="user")

urlpatterns = [
    path(f"{api_base}", include(router.urls)),
    path('schema/openapi.json', SpectacularJSONAPIView.as_view(), name='schema'),
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'),
         name='swagger-ui'),
]

handler500 = "rest_framework.exceptions.server_error"
handler400 = "rest_framework.exceptions.bad_request"
