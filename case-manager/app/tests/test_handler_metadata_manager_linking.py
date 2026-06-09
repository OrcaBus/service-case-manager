import json
import logging
import os
from unittest.mock import patch, MagicMock

# Must be set before handler module is imported (module-level code runs on import)
os.environ.setdefault(
    "METADATA_MANAGER_LINKING_QUEUE_URL",
    "https://sqs.ap-southeast-2.amazonaws.com/123456789/test-queue",
)
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from app.tests.factories import CaseFactory, CASE_REQUEST_FORM_ID_001

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def make_sqs_event(detail_data: dict, message_id: str = "msg-001") -> dict:
    body = {"detail": {"data": detail_data}}
    return {
        "Records": [
            {
                "messageId": message_id,
                "receiptHandle": "fake-receipt-handle",
                "body": json.dumps(body),
            }
        ]
    }


VALID_DATA = {
    "orcabusId": "lib.ABC123",
    "requestFormId": CASE_REQUEST_FORM_ID_001,
}


# Patch the sqs client *object* on the already-imported module, not boto3.client itself.
# This works because by test time the module is loaded and `sqs` is a module-level name.
@patch("handler.metadata_manager_linking.sqs")
class MetadataManagerLinkingHandlerTest(TestCase):
    """
    python manage.py test app.tests.test_handler_metadata_manager_linking
    """

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch("handler.metadata_manager_linking.get_or_create_external_entity")
    @patch("handler.metadata_manager_linking.link_case_to_external_entity_and_emit")
    def test_success_links_case(self, mock_link, mock_get_entity, mock_sqs):
        from handler.metadata_manager_linking import handler

        mock_get_entity.return_value = MagicMock()
        mock_link.return_value = MagicMock()

        handler(make_sqs_event(VALID_DATA), {})

        mock_get_entity.assert_called_once_with("lib.ABC123")
        mock_link.assert_called_once()
        mock_sqs.change_message_visibility.assert_not_called()

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    @patch("handler.metadata_manager_linking.get_or_create_external_entity")
    @patch("handler.metadata_manager_linking.link_case_to_external_entity_and_emit")
    def test_already_linked_is_silent(self, mock_link, mock_get_entity, mock_sqs):
        from django.db import IntegrityError
        from handler.metadata_manager_linking import handler

        mock_get_entity.return_value = MagicMock()
        mock_link.side_effect = IntegrityError("duplicate key")

        handler(make_sqs_event(VALID_DATA), {})  # should NOT raise
        mock_sqs.change_message_visibility.assert_not_called()

    # ------------------------------------------------------------------
    # Case not found yet → extend visibility and re-raise
    # ------------------------------------------------------------------

    def test_case_not_found_extends_visibility_and_raises(self, mock_sqs):
        from handler.metadata_manager_linking import (
            handler,
            VISIBILITY_TIMEOUT_RETRY_SECONDS,
        )

        data = {**VALID_DATA, "requestFormId": "nonexistent-form-id"}

        with self.assertRaises(ObjectDoesNotExist):
            handler(make_sqs_event(data), {})

        mock_sqs.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.ap-southeast-2.amazonaws.com/123456789/test-queue",
            ReceiptHandle="fake-receipt-handle",
            VisibilityTimeout=VISIBILITY_TIMEOUT_RETRY_SECONDS,
        )

    # ------------------------------------------------------------------
    # Invalid / skipped messages
    # ------------------------------------------------------------------

    def test_missing_orcabus_id_skips_silently(self, mock_sqs):
        from handler.metadata_manager_linking import handler

        handler(make_sqs_event({"requestFormId": CASE_REQUEST_FORM_ID_001}), {})
        mock_sqs.change_message_visibility.assert_not_called()

    def test_nan_request_form_id_skips_silently(self, mock_sqs):
        from handler.metadata_manager_linking import handler

        handler(make_sqs_event({"orcabusId": "lib.ABC123", "requestFormId": "nan"}), {})
        mock_sqs.change_message_visibility.assert_not_called()

    def test_malformed_body_skips_silently(self, mock_sqs):
        from handler.metadata_manager_linking import handler

        event = {
            "Records": [{"messageId": "bad", "receiptHandle": "h", "body": "NOT JSON"}]
        }
        handler(event, {})  # should not raise

    # ------------------------------------------------------------------
    # Guard: wrong batch size
    # ------------------------------------------------------------------

    def test_multiple_records_raises(self, mock_sqs):
        from handler.metadata_manager_linking import handler

        event = {
            "Records": [
                {"messageId": "a", "receiptHandle": "h1", "body": "{}"},
                {"messageId": "b", "receiptHandle": "h2", "body": "{}"},
            ]
        }
        with self.assertRaises(ValueError):
            handler(event, {})

    # ------------------------------------------------------------------
    # Unexpected error re-raises
    # ------------------------------------------------------------------

    @patch("handler.metadata_manager_linking.get_or_create_external_entity")
    def test_unexpected_error_reraises(self, mock_get_entity, mock_sqs):
        from handler.metadata_manager_linking import handler

        mock_get_entity.side_effect = RuntimeError("something went wrong")

        with self.assertRaises(RuntimeError):
            handler(make_sqs_event(VALID_DATA), {})
