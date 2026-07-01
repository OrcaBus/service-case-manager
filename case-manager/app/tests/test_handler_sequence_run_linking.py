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

SEQUENCE_RUN_ORCABUS_ID = "seq.01ARZ3NDEKTSV4RRFFQ69G5010"
SEQUENCE_RUN_ID = "r.uY6hEBUmv5x5XUDhkNVxtY"
LIBRARY_ID_1 = "L0000001"
LIBRARY_ID_2 = "L0000002"
LIBRARY_ORCABUS_ID_1 = "lib.01ARZ3NDEKTSV4RRFFQ69G5011"
LIBRARY_ORCABUS_ID_2 = "lib.01ARZ3NDEKTSV4RRFFQ69G5012"
CASE_REQUEST_FORM_ID = "case-test-seq-001"


def make_event(
    sequence_run_id: str = SEQUENCE_RUN_ID,
    linked_libraries: list | None = None,
) -> dict:
    """Build a minimal SequenceRunStateChange EventBridge event."""
    if linked_libraries is None:
        linked_libraries = [LIBRARY_ID_1, LIBRARY_ID_2]
    return {
        "detail-type": "SequenceRunStateChange",
        "source": "orcabus.sequencerunmanager",
        "detail": {
            "sequenceRunId": sequence_run_id,
            "instrumentRunId": "240229_A01052_0172_BHVLMJDMXY",
            "timeStamp": "2024-02-29T10:00:00Z",
            "linkedLibraries": linked_libraries,
        },
    }


class SequenceRunLinkingHandlerTest(TestCase):
    """
    python manage.py test app.tests.test_handler_sequence_run_linking
    """

    def _create_seq_run_entity(self):
        obj, _ = ExternalEntity.objects.get_or_create(
            orcabus_id=SEQUENCE_RUN_ORCABUS_ID,
            prefix="seq",
            type="sequence_run",
            service_name="sequence",
            alias=SEQUENCE_RUN_ID,
        )
        return obj

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID)
        # Create library entity and link it to the case (library is matched by alias)
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

    # ------------------------------------------------------------------
    # Multi-library, same case — deduplicated to a single link
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    @patch("handler.sequence_run_linking.link_case_to_external_entity_and_emit")
    def test_multiple_libraries_same_case_links_once(self, mock_link, mock_get_entity):
        """
        When both libraries in the event are linked to the same case,
        the sequence run should be linked to that case exactly once (deduplicated).
        """
        from handler.sequence_run_linking import handler

        # Link a second library to the same case
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

        mock_seq_entity = MagicMock()
        mock_get_entity.return_value = mock_seq_entity
        mock_link.return_value = MagicMock()

        handler(make_event(), {})  # event carries both LIBRARY_ID_1 and LIBRARY_ID_2

        mock_get_entity.assert_called_once_with(SEQUENCE_RUN_ID)
        # Both libraries point to the same case → link must be called exactly once
        mock_link.assert_called_once_with(
            self.case, mock_seq_entity, history_user="system"
        )

    # ------------------------------------------------------------------
    # Multi-library, different cases — all cases linked
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    def test_multiple_libraries_different_cases_links_all(self, mock_get_entity):
        """
        When each library is linked to a different case, the sequence run should be
        linked to every matched case. Verified against the real DB (no mock on link).
        """
        from handler.sequence_run_linking import handler

        case_2 = CaseFactory(request_form_id="case-test-seq-002")
        library_entity_2 = ExternalEntity.objects.create(
            orcabus_id=LIBRARY_ORCABUS_ID_2,
            prefix="lib",
            type="library",
            service_name="metadata",
            alias=LIBRARY_ID_2,
        )
        CaseExternalEntityLink.objects.create(
            case=case_2, external_entity=library_entity_2
        )

        seq_entity = self._create_seq_run_entity()
        mock_get_entity.return_value = seq_entity

        handler(make_event(), {})

        # get_or_create called once — same entity shared across all case links
        mock_get_entity.assert_called_once_with(SEQUENCE_RUN_ID)

        # Both cases must now be linked to the sequence run in the DB
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=seq_entity
            ).exists(),
            "case 1 should be linked to the sequence run",
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=case_2, external_entity=seq_entity
            ).exists(),
            "case 2 should be linked to the sequence run",
        )

    # ------------------------------------------------------------------
    # Sequence run entity does not yet exist (first time seen)
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    def test_sequence_run_entity_created_when_not_yet_existing(self, mock_get_entity):
        """
        When the sequence run ExternalEntity does not exist yet,
        get_or_create_sequence_run_entity creates it; the link is still persisted.
        """
        from handler.sequence_run_linking import handler

        # Confirm the entity doesn't exist yet
        self.assertFalse(
            ExternalEntity.objects.filter(
                alias=SEQUENCE_RUN_ID, type="sequence_run"
            ).exists()
        )

        # Simulate the service creating the entity on first call
        new_seq_entity = self._create_seq_run_entity()
        mock_get_entity.return_value = new_seq_entity

        handler(make_event(linked_libraries=[LIBRARY_ID_1]), {})

        mock_get_entity.assert_called_once_with(SEQUENCE_RUN_ID)
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=new_seq_entity
            ).exists(),
            "case should be linked to the newly created sequence run entity",
        )

    # ------------------------------------------------------------------
    # No matching case
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    @patch("handler.sequence_run_linking.link_case_to_external_entity_and_emit")
    def test_no_case_for_any_library_skips_silently(self, mock_link, mock_get_entity):
        """No case is linked to any library → warn and return without linking."""
        from handler.sequence_run_linking import handler

        event = make_event(linked_libraries=["L9999999", "L8888888"])
        handler(event, {})

        mock_get_entity.assert_not_called()
        mock_link.assert_not_called()

    # ------------------------------------------------------------------
    # Missing event fields
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    @patch("handler.sequence_run_linking.link_case_to_external_entity_and_emit")
    def test_missing_sequence_run_id_returns_early(self, mock_link, mock_get_entity):
        """Event with no sequenceRunId is silently skipped."""
        from handler.sequence_run_linking import handler

        event = {"detail": {"linkedLibraries": [LIBRARY_ID_1]}}
        handler(event, {})

        mock_get_entity.assert_not_called()
        mock_link.assert_not_called()

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    @patch("handler.sequence_run_linking.link_case_to_external_entity_and_emit")
    def test_missing_linked_libraries_returns_early(self, mock_link, mock_get_entity):
        """Event with no linkedLibraries is silently skipped."""
        from handler.sequence_run_linking import handler

        event = {"detail": {"sequenceRunId": SEQUENCE_RUN_ID, "linkedLibraries": []}}
        handler(event, {})

        mock_get_entity.assert_not_called()
        mock_link.assert_not_called()

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    def test_redelivered_event_does_not_raise_on_existing_link(self, mock_get_entity):
        """
        EventBridge delivers events at-least-once, so the same event may be replayed
        (e.g. after a Lambda retry). The handler is called twice with the same event:
        - First call creates the link in the DB.
        - Second call hits the unique constraint → IntegrityError, must be swallowed.
        """
        from handler.sequence_run_linking import handler

        seq_entity = self._create_seq_run_entity()
        mock_get_entity.return_value = seq_entity

        event = make_event(linked_libraries=[LIBRARY_ID_1])

        handler(event, {})  # first invocation — creates the link
        handler(event, {})  # second invocation (replay) — must NOT raise

    # ------------------------------------------------------------------
    # Http404 propagation (hard failure — Lambda should retry)
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    def test_http404_from_get_or_create_propagates(self, mock_get_entity):
        """Http404 from get_or_create_sequence_run_entity is NOT caught — Lambda should retry."""
        from handler.sequence_run_linking import handler

        mock_get_entity.side_effect = Http404(
            "sequence run not found in sequence service"
        )

        with self.assertRaises(Http404):
            handler(make_event(linked_libraries=[LIBRARY_ID_1]), {})

    # ------------------------------------------------------------------
    # Locked / blocked case states
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    def test_blocked_case_states_skip_link(self, mock_get_entity):
        """ValidationError is caught for all blocked statuses; no link is created."""
        from handler.sequence_run_linking import handler

        user = UserFactory()
        blocked_statuses = [
            CaseStatus.LOCKED,
            CaseStatus.COMPLETED,
            CaseStatus.ARCHIVED,
        ]

        for status in blocked_statuses:
            with self.subTest(status=status):
                State.objects.create(case=self.case, status=status, created_by=user)
                mock_get_entity.return_value = self._create_seq_run_entity()

                handler(
                    make_event(linked_libraries=[LIBRARY_ID_1]), {}
                )  # should NOT raise

                self.assertFalse(
                    CaseExternalEntityLink.objects.filter(
                        case=self.case,
                        external_entity__orcabus_id=SEQUENCE_RUN_ORCABUS_ID,
                    ).exists(),
                    msg=f"Expected no link for status '{status}'",
                )

    # ------------------------------------------------------------------
    # Second library matched (first not linked to any case)
    # ------------------------------------------------------------------

    @patch("handler.sequence_run_linking.get_or_create_sequence_run_entity")
    @patch("handler.sequence_run_linking.link_case_to_external_entity_and_emit")
    def test_matches_second_library_when_first_not_linked(
        self, mock_link, mock_get_entity
    ):
        """
        The event contains two libraries. LIBRARY_ID_1 exists as an entity but has no
        case linked to it (its CaseExternalEntityLink was removed). LIBRARY_ID_2 is
        linked to self.case. The handler iterates all libraries independently, so the
        case is still found and linked via LIBRARY_ID_2.
        """
        from handler.sequence_run_linking import handler

        # Remove the link for LIBRARY_ID_1, link LIBRARY_ID_2 to the case instead
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

        mock_seq_entity = MagicMock()
        mock_get_entity.return_value = mock_seq_entity
        mock_link.return_value = MagicMock()

        handler(make_event(), {})  # event carries both LIBRARY_ID_1 and LIBRARY_ID_2

        mock_get_entity.assert_called_once_with(SEQUENCE_RUN_ID)
        mock_link.assert_called_once_with(
            self.case, mock_seq_entity, history_user="system"
        )
