import logging
from unittest.mock import patch, MagicMock

from django.test import TestCase

from app.models import ExternalEntity, State, CaseExternalEntityLink
from app.models.state import CaseStatus
from app.tests.factories import CaseFactory, UserFactory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed test IDs
# ---------------------------------------------------------------------------

SEQUENCE_RUN_ORCABUS_ID = "seq.01ARZ3NDEKTSV4RRFFQ69G5020"
SEQUENCE_RUN_ID = "r.testStateChangeRun001"
LIBRARY_ID_1 = "L3000001"
LIBRARY_ID_2 = "L3000002"
LIBRARY_ORCABUS_ID_1 = "lib.01ARZ3NDEKTSV4RRFFQ69G5021"
LIBRARY_ORCABUS_ID_2 = "lib.01ARZ3NDEKTSV4RRFFQ69G5022"


def _make_sequence_api_response(runs: list[dict]) -> MagicMock:
    """Build a mock response mimicking the sequence run API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "links": {"next": None, "previous": None},
        "pagination": {"count": len(runs), "page": 1, "rowsPerPage": 100},
        "results": runs,
    }
    return mock_response


class SequencingStateUpdateTest(TestCase):
    """
    python manage.py test app.tests.test_sequencing_state_update
    """

    def setUp(self):
        self.user = UserFactory()
        self.case = CaseFactory(request_form_id="case-state-change-001")

        # Create library entities and link them to the case
        self.library_entity_1 = ExternalEntity.objects.create(
            orcabus_id=LIBRARY_ORCABUS_ID_1,
            prefix="lib",
            type="library",
            service_name="metadata",
            alias=LIBRARY_ID_1,
        )
        self.library_entity_2 = ExternalEntity.objects.create(
            orcabus_id=LIBRARY_ORCABUS_ID_2,
            prefix="lib",
            type="library",
            service_name="metadata",
            alias=LIBRARY_ID_2,
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.library_entity_1
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.library_entity_2
        )

        # Create a sequence run entity and link it to the case
        self.seq_run_entity = ExternalEntity.objects.create(
            orcabus_id=SEQUENCE_RUN_ORCABUS_ID,
            prefix="seq",
            type="sequence_run",
            service_name="sequence",
            alias=SEQUENCE_RUN_ID,
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.seq_run_entity
        )

        # Put the case in "sequencing_started" state (open sequencing round)
        State.objects.create(
            case=self.case,
            status=CaseStatus.SEQUENCING_STARTED,
            created_by=self.user,
        )

    # ------------------------------------------------------------------
    # Happy path: all sequence runs succeeded → state transitions
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_all_runs_succeeded_creates_sequencing_completed(self, mock_get, mock_jwt):
        """
        When all sequence runs for the case's libraries have SUCCEEDED,
        a new 'sequencing_completed' state is created.
        """
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_sequence_api_response(
            [
                {"sequenceRunId": "r.run1", "status": "SUCCEEDED"},
                {"sequenceRunId": "r.run2", "status": "SUCCEEDED"},
            ]
        )

        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 1)

    # ------------------------------------------------------------------
    # Not all runs succeeded → no state transition
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_not_all_runs_succeeded_no_transition(self, mock_get, mock_jwt):
        """
        When at least one sequence run is not SUCCEEDED,
        no state transition should happen.
        """
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_sequence_api_response(
            [
                {"sequenceRunId": "r.run1", "status": "SUCCEEDED"},
                {"sequenceRunId": "r.run2", "status": "STARTED"},
            ]
        )

        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 0)

    # ------------------------------------------------------------------
    # Skip: no open sequencing round (last event is sequencing_completed)
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_skips_when_sequencing_already_completed(self, mock_get, mock_jwt):
        """
        If the most recent sequencing event is 'sequencing_completed',
        the handler should skip (no duplicate transition).
        """
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        # Close the current sequencing round
        State.objects.create(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            created_by=self.user,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_sequence_api_response(
            [
                {"sequenceRunId": "r.run1", "status": "SUCCEEDED"},
            ]
        )

        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        # Should still be only the one we created above (no new one)
        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 1)
        # The API should not have been called
        mock_get.assert_not_called()

    # ------------------------------------------------------------------
    # Skip: no sequencing_started exists at all
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_skips_when_no_sequencing_started(self, mock_get, mock_jwt):
        """
        If the case has never had a sequencing_started state,
        the service should skip.
        """
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        # Remove the sequencing_started state from setUp
        State.objects.filter(
            case=self.case, status=CaseStatus.SEQUENCING_STARTED
        ).delete()

        mock_jwt.return_value = "fake-jwt"
        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        mock_get.assert_not_called()
        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.SEQUENCING_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # Skip: terminal statuses (locked, completed, archived)
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_skips_terminal_statuses(self, mock_get, mock_jwt):
        """Cases in locked, completed, or archived status are skipped."""
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        terminal_statuses = [
            CaseStatus.LOCKED,
            CaseStatus.COMPLETED,
            CaseStatus.ARCHIVED,
        ]

        for status in terminal_statuses:
            with self.subTest(status=status):
                State.objects.create(
                    case=self.case, status=status, created_by=self.user
                )

                mock_jwt.return_value = "fake-jwt"
                update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

                mock_get.assert_not_called()

                # Clean up: archive the terminal state for next subTest
                terminal_state = State.objects.filter(
                    case=self.case, status=status, is_archived=False
                ).first()
                if terminal_state:
                    terminal_state.is_archived = True
                    terminal_state.archived_at = terminal_state.created_at
                    terminal_state.archived_by = self.user
                    terminal_state.save()

    # ------------------------------------------------------------------
    # Skip: missing sequence run entity in DB
    # ------------------------------------------------------------------

    def test_unknown_sequence_run_entity_returns_early(self):
        """If the sequence run hasn't been linked yet, service skips gracefully."""
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        update_sequencing_state_for_sequence_run("r.unknownRunId")

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.SEQUENCING_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # Skip: sequence run entity exists but not linked to any case
    # ------------------------------------------------------------------

    def test_sequence_run_not_linked_to_case_skips(self):
        """Sequence run entity exists but is not linked to any case."""
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        ExternalEntity.objects.create(
            orcabus_id="seq.01ARZ3NDEKTSV4RRFFQ69G5099",
            prefix="seq",
            type="sequence_run",
            service_name="sequence",
            alias="r.orphanRun",
        )

        update_sequencing_state_for_sequence_run("r.orphanRun")

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.SEQUENCING_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # Skip: case has no linked libraries
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_case_with_no_libraries_skips(self, mock_get, mock_jwt):
        """If the case has no library entities linked, skip without calling API."""
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        # Remove library links
        CaseExternalEntityLink.objects.filter(
            case=self.case, external_entity__type="library"
        ).delete()

        mock_jwt.return_value = "fake-jwt"
        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        mock_get.assert_not_called()
        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.SEQUENCING_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # API returns empty results → no transition
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_api_returns_no_results_no_transition(self, mock_get, mock_jwt):
        """If the sequence API returns no runs, no transition happens."""
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_sequence_api_response([])

        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.SEQUENCING_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # API failure (non-200) → no transition
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_api_failure_no_transition(self, mock_get, mock_jwt):
        """If the sequence API returns non-200, no transition happens."""
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.SEQUENCING_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # Second sequencing round: started again after a completed round
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_second_sequencing_round_transitions(self, mock_get, mock_jwt):
        """
        After a completed round (started → completed), a new sequencing_started
        opens a new round. The service should proceed and create a new
        sequencing_completed.
        """
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        # Close the first round
        State.objects.create(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            created_by=self.user,
        )
        # Open a second round
        State.objects.create(
            case=self.case,
            status=CaseStatus.SEQUENCING_STARTED,
            created_by=self.user,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_sequence_api_response(
            [
                {"sequenceRunId": "r.run1", "status": "SUCCEEDED"},
                {"sequenceRunId": "r.run2", "status": "SUCCEEDED"},
            ]
        )

        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        # Should now have 2 sequencing_completed states (one from first round, one new)
        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 2)

    # ------------------------------------------------------------------
    # Idempotency: service called twice for same sequence run
    # ------------------------------------------------------------------

    @patch("app.service.sequencing_state_update.get_service_jwt")
    @patch("app.service.sequencing_state_update.requests.get")
    def test_idempotent_second_call_skips(self, mock_get, mock_jwt):
        """
        After the first invocation creates sequencing_completed, a second
        invocation should skip because the last sequencing event is now completed.
        """
        from app.service.sequencing_state_update import (
            update_sequencing_state_for_sequence_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_sequence_api_response(
            [
                {"sequenceRunId": "r.run1", "status": "SUCCEEDED"},
            ]
        )

        # First call — creates the state
        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)
        # Second call — should skip
        update_sequencing_state_for_sequence_run(SEQUENCE_RUN_ID)

        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.SEQUENCING_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 1)
