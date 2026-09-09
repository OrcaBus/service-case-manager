import json
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase

from app.models import CaseExternalEntityLink, CaseUserLink, ExternalSyncLog
from app.tests.factories import (
    UserFactory,
    USER_002,
    INDIVIDUAL_001,
    ExternalEntityFactory,
    CaseFactory,
    CASE_REQUEST_FORM_ID_001,
    CASE_REQUEST_FORM_ID_002,
)
from app.tests.utils import insert_fixture_1, clear_all_data

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# pragma: allowlist nextline secret
TEST_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJlbWFpbCI6ImpvaG4uZG9lQGV4YW1wbGUuY29tIn0.1XOO35Ozn1XNEj_W7RFefNfJnVm7C1pm7MCEBPbCkJ4"


CASE_BASE_PATH = "api/v1/case"


class ViewSetTestCase(TestCase):
    def setUp(self):
        pass

    def test_get_api(self):
        """
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_get_api
        """
        # case
        insert_fixture_1()

        logger.info(f"check API path for case")
        response = self.client.get(f"/{CASE_BASE_PATH}/")
        self.assertEqual(response.status_code, 200, "Ok status response is expected")

        result_response = response.data["results"]
        case = result_response[0]
        # Spot check external_entity_set
        self.assertEqual(len(case["external_entity_set"]), 2)
        self.assertEqual(
            case["external_entity_set"][0]["external_entity"]["service_name"],
            "metadata",
        )

        # Spot check user_set
        self.assertEqual(len(case["user_set"]), 1)
        self.assertEqual(case["user_set"][0]["description"], "lead")
        self.assertEqual(case["user_set"][0]["user"]["email"], "alice@umccr.org")

    def test_link_relationship(self):
        """
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_link_relationship
        """
        case = insert_fixture_1()

        # case - user
        logger.info(f"check API path for case - user link")

        user_2 = UserFactory(name=USER_002)
        payload = {
            "email": user_2.email,
            "description": "lead",
        }
        response = self.client.post(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/user/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertIsNotNone(
            response.data, "CaseUserLink object is expected to be created"
        )
        expected_keys = {"id", "description", "timestamp", "case", "user"}
        self.assertTrue(
            expected_keys.issubset(response.data.keys()),
            "Expected keys are missing in the object",
        )
        user = case.user_set.get(name=USER_002)
        self.assertEqual(user.name, USER_002, "correct user name assigned")

        # case - external entity
        logger.info(f"check API path for case - external entity link")

        idv_1 = ExternalEntityFactory(**INDIVIDUAL_001)
        payload = {
            "external_entity": idv_1.orcabus_id,
        }
        response = self.client.post(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/external-entity/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        expected_keys = {"id", "timestamp", "case", "external_entity"}
        self.assertTrue(
            expected_keys.issubset(response.data.keys()),
            "Expected keys are missing in the object",
        )

        external_entity_3 = case.external_entity_set.get(alias=INDIVIDUAL_001["alias"])
        self.assertEqual(
            external_entity_3.alias,
            INDIVIDUAL_001["alias"],
            "correct external entity alias assigned",
        )
        self.assertEqual(
            case.external_entity_set.count(),
            3,
            "correct number of external entity linked to case",
        )

    def test_unlink_user(self):
        """
        Test unlinking a user from a case via DELETE.

        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_unlink_user
        """
        case = insert_fixture_1()
        user_2 = UserFactory(name=USER_002)
        # Link user
        CaseUserLink.objects.create(case=case, user=user_2, description="lead")
        self.assertEqual(case.user_set.count(), 2)

        response = self.client.delete(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/user/{user_2.orcabus_id}"
        )
        self.assertEqual(response.status_code, 204)
        case.refresh_from_db()
        self.assertEqual(case.user_set.filter(orcabus_id=user_2.orcabus_id).count(), 0)

    def test_unlink_external_entity(self):
        """
        Test unlinking an external entity from a case via DELETE.
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_unlink_external_entity
        """
        case = insert_fixture_1()
        idv_1 = ExternalEntityFactory(**INDIVIDUAL_001)
        # Link external entity
        CaseExternalEntityLink.objects.create(case=case, external_entity=idv_1)
        self.assertEqual(case.external_entity_set.count(), 3)

        response = self.client.delete(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/external-entity/{idv_1.orcabus_id}"
        )
        self.assertEqual(response.status_code, 204)
        case.refresh_from_db()
        self.assertEqual(
            case.external_entity_set.filter(orcabus_id=idv_1.orcabus_id).count(), 0
        )


class RedcapAutoSyncViewSetTestCase(TestCase):
    """
    Tests for the REDCap auto-sync endpoints:
      POST /api/v1/case/sync-from-redcap/auto
      GET  /api/v1/case/sync-from-redcap/auto/history
    """

    # Shared mock REDCap record payloads
    REDCAP_RECORD_001 = {
        "request_id": CASE_REQUEST_FORM_ID_001,
        "rf_test_requested": "cttso",
    }
    REDCAP_RECORD_002 = {
        "request_id": CASE_REQUEST_FORM_ID_002,
        "rf_test_requested": "wgts",
    }

    # ------------------------------------------------------------------ #
    # POST sync-from-redcap/auto                                           #
    # ------------------------------------------------------------------ #

    @patch("app.service.redcap_import._get_redcap_token", return_value="fake-token")
    @patch("app.service.redcap_import._post")
    def test_sync_from_redcap_auto_creates_cases(self, mock_post, _mock_token):
        """
        POST sync-from-redcap/auto with no prior sync log (full range) should
        call REDCap, create cases, and return synced/failed counts.

        python manage.py test app.tests.test_viewsets.RedcapAutoSyncViewSetTestCase.test_sync_from_redcap_auto_creates_cases
        """
        mock_post.return_value = [self.REDCAP_RECORD_001, self.REDCAP_RECORD_002]

        response = self.client.post(f"/{CASE_BASE_PATH}/sync-from-redcap/auto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["synced"], 2)
        self.assertEqual(response.data["failed"], 0)

        # A sync log entry must have been created
        self.assertEqual(
            ExternalSyncLog.objects.filter(external_service="redcap").count(), 1
        )

    @patch("app.service.redcap_import._get_redcap_token", return_value="fake-token")
    @patch("app.service.redcap_import._post")
    def test_sync_from_redcap_auto_uses_last_sync_as_cursor(
        self, mock_post, _mock_token
    ):
        """
        When a prior ExternalSyncLog exists, the auto-sync should start from
        that timestamp (cursor behaviour). A second log entry is appended.

        python manage.py test app.tests.test_viewsets.RedcapAutoSyncViewSetTestCase.test_sync_from_redcap_auto_uses_last_sync_as_cursor
        """
        prior_ts = datetime.now(timezone.utc) - timedelta(hours=2)
        ExternalSyncLog.objects.create(external_service="redcap", imported_at=prior_ts)

        mock_post.return_value = [self.REDCAP_RECORD_001]

        response = self.client.post(f"/{CASE_BASE_PATH}/sync-from-redcap/auto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["synced"], 1)

        # Two log entries now: the seed + the one created by this sync
        self.assertEqual(
            ExternalSyncLog.objects.filter(external_service="redcap").count(), 2
        )

    @patch("app.service.redcap_import._get_redcap_token", return_value="fake-token")
    @patch("app.service.redcap_import._post")
    def test_sync_from_redcap_auto_partial_failure(self, mock_post, _mock_token):
        """
        Records that fail mapping (unknown rf_test_requested) are counted as
        failed without aborting the batch. The sync log is still written.

        python manage.py test app.tests.test_viewsets.RedcapAutoSyncViewSetTestCase.test_sync_from_redcap_auto_partial_failure
        """
        bad_record = {"request_id": "case-bad", "rf_test_requested": "99"}
        mock_post.return_value = [self.REDCAP_RECORD_001, bad_record]

        response = self.client.post(f"/{CASE_BASE_PATH}/sync-from-redcap/auto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["synced"], 1)
        self.assertEqual(response.data["failed"], 1)
        # Sync log still written despite partial failure (atomic wraps the whole call)
        self.assertEqual(
            ExternalSyncLog.objects.filter(external_service="redcap").count(), 1
        )

    @patch("app.service.redcap_import._get_redcap_token", return_value="fake-token")
    @patch("app.service.redcap_import._post")
    def test_sync_from_redcap_auto_empty_redcap_response(self, mock_post, _mock_token):
        """
        When REDCap returns no records the endpoint should still return 200
        with synced=0 and write a sync log.

        python manage.py test app.tests.test_viewsets.RedcapAutoSyncViewSetTestCase.test_sync_from_redcap_auto_empty_redcap_response
        """
        mock_post.return_value = []

        response = self.client.post(f"/{CASE_BASE_PATH}/sync-from-redcap/auto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["synced"], 0)
        self.assertEqual(response.data["failed"], 0)
        self.assertEqual(
            ExternalSyncLog.objects.filter(external_service="redcap").count(), 1
        )


class CaseIsActiveFilterTestCase(TestCase):
    """
    Tests for the ?isActive= query param on GET /api/v1/case/.

    Semantics (see CaseManager.filter_by_active):
      - omitted        -> no state filtering, all cases returned
      - isActive=true  -> only ACTIVE cases: latest non-archived state is
                          non-terminal, OR the case has no state at all, AND the
                          case has no archived state record
      - isActive=false -> only INACTIVE cases: latest non-archived state is
                          terminal (locked/completed/archived), OR the case has
                          any archived state record

    python manage.py test app.tests.test_viewsets.CaseIsActiveFilterTestCase
    """

    def setUp(self):
        from datetime import date, timedelta
        from app.tests.factories import CaseFactory, StateFactory, UserFactory
        from app.models.state import CaseStatus

        clear_all_data()

        self.user = UserFactory(name="Alice")
        self.day1 = date(2024, 1, 1)
        self.day2 = date(2024, 1, 2)

        def add_state(case, status, event_date, is_archived=False):
            return StateFactory(
                case=case,
                status=status,
                created_by=self.user,
                event_date=event_date,
                is_archived=is_archived,
            )

        # 1. Active: latest non-archived state is non-terminal.
        self.active_case = CaseFactory(request_form_id="case-active")
        add_state(self.active_case, CaseStatus.SEQUENCING_STARTED, self.day1)

        # 2. Stateless: no state at all -> treated as active.
        self.stateless_case = CaseFactory(request_form_id="case-stateless")

        # 3. Inactive by terminal latest state (completed).
        self.terminal_case = CaseFactory(request_form_id="case-terminal")
        add_state(self.terminal_case, CaseStatus.SEQUENCING_STARTED, self.day1)
        add_state(self.terminal_case, CaseStatus.COMPLETED, self.day2)

    def _get_form_ids(self, response):
        return {c["request_form_id"] for c in response.data["results"]}

    def test_omitted_returns_all_cases(self):
        """No isActive param -> every case is returned regardless of state."""
        response = self.client.get(f"/{CASE_BASE_PATH}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._get_form_ids(response),
            {
                "case-active",
                "case-stateless",
                "case-terminal",
            },
        )

    def test_is_active_true_returns_only_active(self):
        """isActive=true -> active + stateless."""
        response = self.client.get(f"/{CASE_BASE_PATH}/?isActive=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._get_form_ids(response),
            {"case-active", "case-stateless"},
        )

    def test_is_active_false_returns_only_inactive(self):
        """isActive=false -> terminal-latest OR has-archived-state cases only."""
        response = self.client.get(f"/{CASE_BASE_PATH}/?isActive=false")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._get_form_ids(response),
            {"case-terminal"},
        )

    def test_true_and_false_are_complements(self):
        """Every case appears in exactly one of isActive=true / isActive=false."""
        active = self._get_form_ids(
            self.client.get(f"/{CASE_BASE_PATH}/?isActive=true")
        )
        inactive = self._get_form_ids(
            self.client.get(f"/{CASE_BASE_PATH}/?isActive=false")
        )
        self.assertEqual(active & inactive, set(), "buckets must not overlap")
        self.assertEqual(
            active | inactive,
            {
                "case-active",
                "case-stateless",
                "case-terminal",
            },
            "buckets must together cover all cases",
        )
