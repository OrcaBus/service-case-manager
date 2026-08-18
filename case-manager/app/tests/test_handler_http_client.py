import logging
from unittest.mock import patch, MagicMock
from django.test import TestCase

logger = logging.getLogger(__name__)


class HttpClientTest(TestCase):
    """
    Tests for app/service/http_client.py utilities.

    python manage.py test app.tests.test_handler_http_client
    """

    @patch("app.service.http_client.get_service_jwt")
    def test_get_authenticated_headers_success(self, mock_get_jwt):
        """Verify headers are constructed correctly with JWT token."""
        from app.service.http_client import get_authenticated_headers

        mock_get_jwt.return_value = "test-jwt-token-12345"

        headers = get_authenticated_headers()

        self.assertEqual(headers, {"Authorization": "Bearer test-jwt-token-12345"})
        mock_get_jwt.assert_called_once()

    @patch("app.service.http_client.requests.get")
    @patch("app.service.http_client.get_service_jwt")
    def test_http_get_json_success(self, mock_get_jwt, mock_requests_get):
        """Verify successful HTTP GET returns parsed JSON using the JWT token."""
        from app.service.http_client import http_get_json

        mock_get_jwt.return_value = "test-jwt-token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"id": "123", "name": "test"}]}
        mock_requests_get.return_value = mock_response

        result = http_get_json("https://example.com/api/endpoint")

        self.assertEqual(result, {"results": [{"id": "123", "name": "test"}]})
        mock_requests_get.assert_called_once_with(
            "https://example.com/api/endpoint",
            headers={"Authorization": "Bearer test-jwt-token"},
            params=None,
            timeout=30,
        )
