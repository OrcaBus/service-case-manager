import logging
from unittest.mock import patch

from django.test import TestCase

from app.models import CaseExternalEntityLink
from app.schemas.events.case_srelationship_state_change_model import (
    Action,
    DetailType,
)
from app.service.case import (
    link_case_to_external_entity_and_emit,
    unlink_case_to_external_entity_and_emit,
)
from app.tests.factories import (
    CaseFactory,
    ExternalEntityFactory,
    CASE_REQUEST_FORM_ID_001,
    CASE_REQUEST_FORM_ID_002,
    LIBRARY_001,
    LIBRARY_002,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LinkCaseToExternalEntityAndEmitTestCase(TestCase):
    """
    python manage.py test app.tests.test_case_service.LinkCaseToExternalEntityAndEmitTestCase
    """

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self.external_entity = ExternalEntityFactory(**LIBRARY_001)

    @patch("app.service.case.emit_event")
    def test_link_creates_db_record_and_emits_create_event(self, mock_emit):
        """
        python manage.py test app.tests.test_case_service.LinkCaseToExternalEntityAndEmitTestCase.test_link_creates_db_record_and_emits_create_event

        Linking a case to an external entity should persist the CaseExternalEntityLink
        and emit a CREATE event containing the case and external entity details.
        """
        with self.captureOnCommitCallbacks(execute=True):
            link = link_case_to_external_entity_and_emit(
                case=self.case,
                external_entity=self.external_entity,
                history_user="alice@umccr.org",
            )

        # DB record created
        self.assertIsNotNone(link.pk)
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=self.external_entity
            ).exists()
        )

        # Event emitted once with correct detail_type
        mock_emit.assert_called_once()
        _, kwargs = mock_emit.call_args
        self.assertEqual(
            kwargs["detail_type"], DetailType.CaseRelationshipStateChange.value
        )

        event = kwargs["event_detail_model"]
        self.assertEqual(event.action, Action.CREATE)
        self.assertEqual(event.refId, str(link.pk))

        # Event payload contains full case and external entity data
        self.assertEqual(str(event.case["orcabus_id"]), str(self.case.orcabus_id))
        self.assertEqual(event.case["request_form_id"], self.case.request_form_id)
        self.assertEqual(
            str(event.externalEntity["orcabus_id"]),
            str(self.external_entity.orcabus_id),
        )
        self.assertEqual(event.externalEntity["alias"], self.external_entity.alias)
        self.assertEqual(
            event.externalEntity["service_name"], self.external_entity.service_name
        )
        self.assertEqual(event.externalEntity["type"], self.external_entity.type)


class UnlinkCaseToExternalEntityAndEmitTestCase(TestCase):
    """
    python manage.py test app.tests.test_case_service.UnlinkCaseToExternalEntityAndEmitTestCase
    """

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_002)
        self.external_entity = ExternalEntityFactory(**LIBRARY_002)
        self.link = CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.external_entity
        )

    @patch("app.service.case.emit_event")
    def test_unlink_removes_db_record_and_emits_delete_event(self, mock_emit):
        """
        python manage.py test app.tests.test_case_service.UnlinkCaseToExternalEntityAndEmitTestCase.test_unlink_removes_db_record_and_emits_delete_event

        Unlinking should delete the CaseExternalEntityLink and emit a DELETE event
        containing the case and external entity details captured before deletion.
        """
        link_pk = str(self.link.pk)

        with self.captureOnCommitCallbacks(execute=True):
            unlink_case_to_external_entity_and_emit(
                case_external_entity=self.link,
                history_user="bob@umccr.org",
            )

        # DB record removed
        self.assertFalse(CaseExternalEntityLink.objects.filter(pk=link_pk).exists())

        # Event emitted once with correct detail_type
        mock_emit.assert_called_once()
        _, kwargs = mock_emit.call_args
        self.assertEqual(
            kwargs["detail_type"], DetailType.CaseRelationshipStateChange.value
        )

        event = kwargs["event_detail_model"]
        self.assertEqual(event.action, Action.DELETE)
        self.assertEqual(event.refId, link_pk)

        # Event payload contains full case and external entity data (captured before deletion)
        self.assertEqual(str(event.case["orcabus_id"]), str(self.case.orcabus_id))
        self.assertEqual(event.case["request_form_id"], self.case.request_form_id)
        self.assertEqual(
            str(event.externalEntity["orcabus_id"]),
            str(self.external_entity.orcabus_id),
        )
        self.assertEqual(event.externalEntity["alias"], self.external_entity.alias)
