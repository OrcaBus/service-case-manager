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

from app.models import ExternalEntity, PendingExternalEntity, CaseExternalEntityLink
from app.tests.factories import (
    CaseFactory,
    ExternalEntityFactory,
    CASE_REQUEST_FORM_ID_001,
)

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


SAMPLE_BASED_DATA = {
    "orcabusId": "lib.00000000000000000000000001",
    "libraryId": "LIB001",
    "sample": {
        "orcabusId": "smp.00000000000000000000SMP001",
        "sampleId": "SMP001",
    },
    # no requestFormId
}


@patch("handler.metadata_manager_linking.sqs")
class SampleBasedLinkingTest(TestCase):
    """
    Tests for the sample-based linking fallback path (no requestFormId).

    python manage.py test app.tests.test_handler_metadata_manager_linking.SampleBasedLinkingTest
    """

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)

    # ------------------------------------------------------------------
    # PendingExternalEntity → promoted and linked
    # ------------------------------------------------------------------

    def test_pending_sample_is_promoted_and_library_linked(self, mock_sqs):
        """
        A PendingExternalEntity for the sample should be promoted to a real
        ExternalEntity, the sample linked to the case, the pending record
        deleted, and the library upserted and linked to the same case.
        """
        from handler.metadata_manager_linking import handler

        PendingExternalEntity.objects.create(
            case=self.case,
            alias="SMP001",
            type="sample",
            service_name="metadata",
        )

        handler(make_sqs_event(SAMPLE_BASED_DATA), {})

        # PendingExternalEntity must be gone
        self.assertFalse(PendingExternalEntity.objects.filter(alias="SMP001").exists())

        # Sample ExternalEntity must exist
        sample_entity = ExternalEntity.objects.get(
            orcabus_id="smp.00000000000000000000SMP001"
        )
        self.assertEqual(sample_entity.alias, "SMP001")
        self.assertEqual(sample_entity.type, "sample")
        self.assertEqual(sample_entity.service_name, "metadata")

        # Library ExternalEntity must exist
        lib_entity = ExternalEntity.objects.get(
            orcabus_id="lib.00000000000000000000000001"
        )
        self.assertEqual(lib_entity.alias, "LIB001")
        self.assertEqual(lib_entity.type, "library")

        # Both must be linked to the case
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=sample_entity
            ).exists()
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=lib_entity
            ).exists()
        )

        mock_sqs.change_message_visibility.assert_not_called()

    # ------------------------------------------------------------------
    # ExternalEntity already resolved → only library linked
    # ------------------------------------------------------------------

    def test_resolved_sample_entity_links_library(self, mock_sqs):
        """
        When sample.sampleId is already in ExternalEntity (linked to a case),
        the handler should upsert the library entity and link it to the same case.
        """
        from handler.metadata_manager_linking import handler

        sample_entity = ExternalEntity.objects.create(
            orcabus_id="smp.00000000000000000000SMP001",
            alias="SMP001",
            type="sample",
            service_name="metadata",
            prefix="smp",
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=sample_entity
        )

        handler(make_sqs_event(SAMPLE_BASED_DATA), {})

        lib_entity = ExternalEntity.objects.get(
            orcabus_id="lib.00000000000000000000000001"
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=lib_entity
            ).exists()
        )
        mock_sqs.change_message_visibility.assert_not_called()

    # ------------------------------------------------------------------
    # Skip / retry cases
    # ------------------------------------------------------------------

    def test_sample_not_found_extends_visibility_and_raises(self, mock_sqs):
        """No match in ExternalEntity or PendingExternalEntity → SQS retry."""
        from handler.metadata_manager_linking import (
            handler,
            VISIBILITY_TIMEOUT_RETRY_SECONDS,
        )

        with self.assertRaises(ObjectDoesNotExist):
            handler(make_sqs_event(SAMPLE_BASED_DATA), {})

        mock_sqs.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.ap-southeast-2.amazonaws.com/123456789/test-queue",
            ReceiptHandle="fake-receipt-handle",
            VisibilityTimeout=VISIBILITY_TIMEOUT_RETRY_SECONDS,
        )
