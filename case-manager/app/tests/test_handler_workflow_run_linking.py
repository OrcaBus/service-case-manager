import logging
from unittest.mock import patch, MagicMock

from rest_framework.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from django.test import TestCase

from app.models import ExternalEntity, State
from app.models.case import CaseExternalEntityLink
from app.models.state import CaseStatus
from app.tests.factories import CaseFactory, UserFactory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed test IDs — fake values, same format as real OrcaBus IDs
# ---------------------------------------------------------------------------

WORKFLOW_RUN_ORCABUS_ID = "wfr.01ARZ3NDEKTSV4RRFFQ69G5001"
LIBRARY_ORCABUS_ID_1 = "lib.01ARZ3NDEKTSV4RRFFQ69G5002"
LIBRARY_ORCABUS_ID_2 = "lib.01ARZ3NDEKTSV4RRFFQ69G5003"
LIBRARY_ID_1 = "L0000001"
LIBRARY_ID_2 = "L0000002"
CASE_REQUEST_FORM_ID = "case-test-wfr-001"


def make_event(
    workflow_run_orcabus_id: str = WORKFLOW_RUN_ORCABUS_ID,
    libraries: list | None = None,
) -> dict:
    """Build a minimal WorkflowRunStateChange EventBridge event."""
    if libraries is None:
        libraries = [
            {"libraryId": LIBRARY_ID_1, "orcabusId": LIBRARY_ORCABUS_ID_1},
            {"libraryId": LIBRARY_ID_2, "orcabusId": LIBRARY_ORCABUS_ID_2},
        ]
    return {
        "detail-type": "WorkflowRunStateChange",
        "source": "orcabus.sash",
        "detail": {
            "orcabusId": workflow_run_orcabus_id,
            "libraries": libraries,
        },
    }

    def _create_wfr_entity(self):
        obj, _ = ExternalEntity.objects.get_or_create(
            orcabus_id=WORKFLOW_RUN_ORCABUS_ID,
            prefix="wfr",
            type="workflow_run",
            service_name="workflow",
            alias="portal-test-run-001",
        )
        return obj


class WorkflowRunLinkingHandlerTest(TestCase):
    """
    python manage.py test app.tests.test_handler_workflow_run_linking
    """

    def _create_wfr_entity(self):
        obj, _ = ExternalEntity.objects.get_or_create(
            orcabus_id=WORKFLOW_RUN_ORCABUS_ID,
            prefix="wfr",
            type="workflow_run",
            service_name="workflow",
            alias="portal-test-run-001",
        )
        return obj

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID)
        self.library_entity = ExternalEntity.objects.create(
            orcabus_id=LIBRARY_ORCABUS_ID_1,
            prefix="lib",
            type="library",
            service_name="metadata",
            alias=LIBRARY_ID_1,
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.library_entity
        )

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    @patch("handler.workflow_run_linking.link_case_to_external_entity_and_emit")
    def test_links_workflow_run_when_library_matched(self, mock_link, mock_get_entity):
        """Workflow run is linked to the case that owns the matching library."""
        from handler.workflow_run_linking import handler

        mock_wfr_entity = MagicMock()
        mock_get_entity.return_value = mock_wfr_entity
        mock_link.return_value = MagicMock()

        handler(make_event(), {})

        mock_get_entity.assert_called_once_with(WORKFLOW_RUN_ORCABUS_ID)
        mock_link.assert_called_once_with(
            self.case, mock_wfr_entity, history_user="system"
        )

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    @patch("handler.workflow_run_linking.link_case_to_external_entity_and_emit")
    def test_matches_second_library_when_first_not_linked(
        self, mock_link, mock_get_entity
    ):
        """Falls through to the second library if the first has no linked case."""
        from handler.workflow_run_linking import handler

        CaseExternalEntityLink.objects.filter(
            external_entity=self.library_entity
        ).delete()
        library_entity_2 = ExternalEntity.objects.create(
            orcabus_id=LIBRARY_ORCABUS_ID_2,
            prefix="lib",
            type="library",
            service_name="metadata",
            alias=LIBRARY_ID_2,
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=library_entity_2
        )

        mock_wfr_entity = MagicMock()
        mock_get_entity.return_value = mock_wfr_entity
        mock_link.return_value = MagicMock()

        handler(make_event(), {})

        mock_get_entity.assert_called_once_with(WORKFLOW_RUN_ORCABUS_ID)
        mock_link.assert_called_once_with(
            self.case, mock_wfr_entity, history_user="system"
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    @patch("handler.workflow_run_linking.link_case_to_external_entity_and_emit")
    def test_already_linked_workflow_run_is_silent(self, mock_link, mock_get_entity):
        """IntegrityError (duplicate link) is caught and logged — not re-raised."""
        from handler.workflow_run_linking import handler

        mock_get_entity.return_value = MagicMock()
        mock_link.side_effect = IntegrityError("duplicate key")

        handler(make_event(), {})  # should NOT raise

    # ------------------------------------------------------------------
    # No matching case
    # ------------------------------------------------------------------

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    @patch("handler.workflow_run_linking.link_case_to_external_entity_and_emit")
    def test_no_case_for_any_library_skips_silently(self, mock_link, mock_get_entity):
        """No case is linked to any library → warn and return without linking."""
        from handler.workflow_run_linking import handler

        event = make_event(
            libraries=[
                {"libraryId": "L9999999", "orcabusId": "lib.01ARZ3NDEKTSV4RRFFQ69G5001"}
            ]
        )
        handler(event, {})

        mock_get_entity.assert_not_called()
        mock_link.assert_not_called()

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    def test_http404_from_get_or_create_propagates(self, mock_get_entity):
        """Http404 from get_or_create_external_entity is NOT caught — Lambda should retry."""
        from handler.workflow_run_linking import handler

        mock_get_entity.side_effect = Http404("workflow run not found")

        with self.assertRaises(Http404):
            handler(make_event(), {})

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    def test_locked_case_skips_link(self, mock_get_entity):
        """ValidationError from the model is caught; no link is created for a locked case."""
        from handler.workflow_run_linking import handler

        user = UserFactory()
        State.objects.create(case=self.case, status=CaseStatus.LOCKED, created_by=user)
        mock_get_entity.return_value = self._create_wfr_entity()

        handler(make_event(), {})  # should NOT raise

        self.assertFalse(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity__orcabus_id=WORKFLOW_RUN_ORCABUS_ID
            ).exists()
        )

    @patch("handler.workflow_run_linking.get_or_create_external_entity")
    def test_blocked_case_states_skip_link(self, mock_get_entity):
        """ValidationError from the model is caught for all blocked statuses; no link is created."""
        from handler.workflow_run_linking import handler

        user = UserFactory()
        blocked_statuses = [
            CaseStatus.LOCKED,
            CaseStatus.COMPLETED,
            CaseStatus.ARCHIVED,
        ]

        for status in blocked_statuses:
            with self.subTest(status=status):
                State.objects.create(case=self.case, status=status, created_by=user)
                mock_get_entity.return_value = self._create_wfr_entity()

                handler(make_event(), {})  # should NOT raise

                self.assertFalse(
                    CaseExternalEntityLink.objects.filter(
                        case=self.case,
                        external_entity__orcabus_id=WORKFLOW_RUN_ORCABUS_ID,
                    ).exists(),
                    msg=f"Expected no link for status '{status}'",
                )

    def test_model_raises_validation_error_directly_for_locked_case(self):
        """CaseExternalEntityLink.save() itself raises ValidationError — model-level enforcement."""
        user = UserFactory()
        State.objects.create(case=self.case, status=CaseStatus.LOCKED, created_by=user)
        wfr_entity = self._create_wfr_entity()

        with self.assertRaises(DjangoValidationError):
            CaseExternalEntityLink.objects.create(
                case=self.case, external_entity=wfr_entity
            )
