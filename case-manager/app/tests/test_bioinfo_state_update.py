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

WORKFLOW_RUN_ORCABUS_ID_1 = "wfr.01ARZ3NDEKTSV4RRFFQ69G5001"
WORKFLOW_RUN_ORCABUS_ID_2 = "wfr.01ARZ3NDEKTSV4RRFFQ69G5002"
WORKFLOW_RUN_ORCABUS_ID_3 = "wfr.01ARZ3NDEKTSV4RRFFQ69G5003"


def _make_workflow_api_response(runs: list[dict]) -> MagicMock:
    """Build a mock response mimicking the workflow run API (is_ongoing filter)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "links": {"next": None, "previous": None},
        "pagination": {"count": len(runs), "page": 1, "rowsPerPage": 100},
        "results": runs,
    }
    return mock_response


class BioinfoStateUpdateTest(TestCase):
    """
    python manage.py test app.tests.test_bioinfo_state_update
    """

    def setUp(self):
        self.user = UserFactory()
        self.case = CaseFactory(request_form_id="case-bioinfo-state-001")

        # Create two workflow run entities and link them to the case.
        self.wfr_entity_1 = ExternalEntity.objects.create(
            orcabus_id=WORKFLOW_RUN_ORCABUS_ID_1,
            prefix="wfr",
            type="workflow_run",
            service_name="workflow",
            alias="wfr.run1",
        )
        self.wfr_entity_2 = ExternalEntity.objects.create(
            orcabus_id=WORKFLOW_RUN_ORCABUS_ID_2,
            prefix="wfr",
            type="workflow_run",
            service_name="workflow",
            alias="wfr.run2",
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.wfr_entity_1
        )
        CaseExternalEntityLink.objects.create(
            case=self.case, external_entity=self.wfr_entity_2
        )

        # Put the case in "bioinformatics_started".
        State.objects.create(
            case=self.case,
            status=CaseStatus.BIOINFORMATICS_STARTED,
            created_by=self.user,
        )

    # ------------------------------------------------------------------
    # Bulk query: a single API call with all workflow run ids
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_bulk_query_sends_all_orcabus_ids_in_one_call(self, mock_get, mock_jwt):
        """
        All linked workflow run ids should be sent in a single API call via a
        multi-value orcabusId param, rather than one request per run.
        """
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        mock_jwt.return_value = "fake-jwt"
        # No runs ongoing -> empty results.
        mock_get.return_value = _make_workflow_api_response([])

        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

        # Exactly one API call for the whole set of workflow runs.
        mock_get.assert_called_once()
        _, call_kwargs = mock_get.call_args
        params = call_kwargs["params"]
        self.assertEqual(params["is_ongoing"], "true")
        self.assertCountEqual(
            params["orcabusId"],
            [WORKFLOW_RUN_ORCABUS_ID_1, WORKFLOW_RUN_ORCABUS_ID_2],
        )

    # ------------------------------------------------------------------
    # All runs finished -> bioinformatics_completed
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_all_runs_finished_creates_bioinformatics_completed(
        self, mock_get, mock_jwt
    ):
        """When no workflow run is ongoing, transition to bioinformatics_completed."""
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_workflow_api_response([])

        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.BIOINFORMATICS_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 1)

    # ------------------------------------------------------------------
    # At least one run ongoing -> stays bioinformatics_started (no new state)
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_one_run_ongoing_no_transition_when_already_started(
        self, mock_get, mock_jwt
    ):
        """
        If any run is still ongoing, the target is bioinformatics_started. Since
        the case is already in that status, no new state is created.
        """
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_workflow_api_response(
            [{"orcabusId": WORKFLOW_RUN_ORCABUS_ID_2, "status": "RUNNING"}]
        )

        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.BIOINFORMATICS_COMPLETED
            ).exists()
        )
        # Still exactly one started state, no duplicate created.
        self.assertEqual(
            State.objects.filter(
                case=self.case,
                status=CaseStatus.BIOINFORMATICS_STARTED,
                is_archived=False,
            ).count(),
            1,
        )

    # ------------------------------------------------------------------
    # Ongoing run transitions completed case back to started
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_ongoing_run_transitions_completed_back_to_started(
        self, mock_get, mock_jwt
    ):
        """
        If the case is currently bioinformatics_completed but a run becomes
        ongoing again, a new bioinformatics_started state is created.
        """
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        # Move the case to completed first.
        State.objects.create(
            case=self.case,
            status=CaseStatus.BIOINFORMATICS_COMPLETED,
            created_by=self.user,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_workflow_api_response(
            [{"orcabusId": WORKFLOW_RUN_ORCABUS_ID_1, "status": "RUNNING"}]
        )

        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

        # A second bioinformatics_started should now exist.
        self.assertEqual(
            State.objects.filter(
                case=self.case,
                status=CaseStatus.BIOINFORMATICS_STARTED,
                is_archived=False,
            ).count(),
            2,
        )

    # ------------------------------------------------------------------
    # Skip: terminal statuses (locked, completed, archived)
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_skips_terminal_statuses(self, mock_get, mock_jwt):
        """Cases in locked, completed, or archived status are skipped."""
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
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
                update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

                mock_get.assert_not_called()

                # Clean up: archive the terminal state for the next subTest.
                terminal_state = State.objects.filter(
                    case=self.case, status=status, is_archived=False
                ).first()
                if terminal_state:
                    terminal_state.is_archived = True
                    terminal_state.archived_at = terminal_state.created_at
                    terminal_state.archived_by = self.user
                    terminal_state.save()

    # ------------------------------------------------------------------
    # Skip: missing workflow run entity in DB
    # ------------------------------------------------------------------

    def test_unknown_workflow_run_entity_returns_early(self):
        """If the workflow run hasn't been linked yet, service skips gracefully."""
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        update_bioinfo_state_for_workflow_run("wfr.01UNKNOWN0000000000000000")

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.BIOINFORMATICS_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # Skip: workflow run entity exists but not linked to any case
    # ------------------------------------------------------------------

    def test_workflow_run_not_linked_to_case_skips(self):
        """Workflow run entity exists but is not linked to any case."""
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        ExternalEntity.objects.create(
            orcabus_id=WORKFLOW_RUN_ORCABUS_ID_3,
            prefix="wfr",
            type="workflow_run",
            service_name="workflow",
            alias="wfr.orphanRun",
        )

        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_3)

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.BIOINFORMATICS_COMPLETED
            ).exists()
        )

    # ------------------------------------------------------------------
    # Idempotency: second call after completion skips
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_idempotent_second_call_skips(self, mock_get, mock_jwt):
        """
        After the first invocation creates bioinformatics_completed, a second
        invocation with the same (all-finished) result should not duplicate it.
        """
        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_get.return_value = _make_workflow_api_response([])

        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)
        update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

        completed_states = State.objects.filter(
            case=self.case,
            status=CaseStatus.BIOINFORMATICS_COMPLETED,
            is_archived=False,
        )
        self.assertEqual(completed_states.count(), 1)

    # ------------------------------------------------------------------
    # API failure propagates (hard failure so the Lambda can retry)
    # ------------------------------------------------------------------

    @patch("app.service.bioinfo_state_update.get_service_jwt")
    @patch("app.service.bioinfo_state_update.requests.get")
    def test_api_failure_raises_and_no_transition(self, mock_get, mock_jwt):
        """
        A failed workflow API call should raise (via raise_for_status) so the
        caller can retry, and no state transition should be persisted.
        """
        import requests

        from app.service.bioinfo_state_update import (
            update_bioinfo_state_for_workflow_run,
        )

        mock_jwt.return_value = "fake-jwt"
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.RequestException(
            "boom"
        )
        mock_get.return_value = mock_response

        with self.assertRaises(requests.RequestException):
            update_bioinfo_state_for_workflow_run(WORKFLOW_RUN_ORCABUS_ID_1)

        self.assertFalse(
            State.objects.filter(
                case=self.case, status=CaseStatus.BIOINFORMATICS_COMPLETED
            ).exists()
        )
