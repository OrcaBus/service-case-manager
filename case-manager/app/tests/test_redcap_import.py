"""
Tests for app.service.redcap_import sync functions:
  - upsert_redcap_records_by_date_range (batch fetch + upsert)
  - upsert_case_from_redcap_record (single record -> Case/State/due_date logic)

python manage.py test app.tests.test_redcap_import
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from app.models import Case, State
from app.models.case import CaseType, CaseStudyType
from app.models.state import CaseStatus
from app.service.redcap_import import (
    upsert_redcap_records_by_date_range,
    upsert_case_from_redcap_record,
    SHORT_TURNAROUND_STUDY_NAMES,
    SHORT_TURNAROUND_WEEKS,
    DEFAULT_TURNAROUND_WEEKS,
)
from app.tests.factories import CaseFactory


class UpsertRedcapRecordsByDateRangeSingleRecordTest(TestCase):
    """
    One REDCap record fetched -> one Case successfully synced into the DB.

    python manage.py test app.tests.test_redcap_import.UpsertRedcapRecordsByDateRangeSingleRecordTest
    """

    def setUp(self):
        self.record = {
            "request_id": "case-001",
            "rf_test_requested": CaseType.CTTSO,
            "rf_study": "TestStudy",
            "rf_study_id": "STUDY-01",
            "rf_ur": "UR12345",
            "nata_accred_report": "1",
            "cttso_receipt_date": "2026-07-01",
            "cttso_receipt_time": "09:30",
        }

    @patch("app.service.redcap_import.get_redcap_record_by_date_range")
    def test_single_record_synced_successfully(self, mock_get_records):
        """
        python manage.py test app.tests.test_redcap_import.UpsertRedcapRecordsByDateRangeSingleRecordTest.test_single_record_synced_successfully
        """
        mock_get_records.return_value = [self.record]

        result = upsert_redcap_records_by_date_range(after_date="2026-07-01 00:00:00")

        self.assertEqual(result, {"synced": 1, "failed": 0})

        case = Case.objects.get(request_form_id="case-001")
        self.assertEqual(case.type, CaseType.CTTSO)
        self.assertEqual(case.study_type, CaseStudyType.CLINICAL)
        self.assertEqual(case.study_name, "TestStudy")
        self.assertEqual(case.study_id, "STUDY-01")
        self.assertEqual(case.ur_number, "UR12345")
        self.assertTrue(case.is_nata_accredited)


class UpsertRedcapRecordsByDateRangeBatchTest(TestCase):
    """
    Batch behaviour: multiple records, partial failure, empty list.

    python manage.py test app.tests.test_redcap_import.UpsertRedcapRecordsByDateRangeBatchTest
    """

    @patch("app.service.redcap_import.get_redcap_record_by_date_range")
    def test_all_records_synced(self, mock_get_records):
        """
        python manage.py test app.tests.test_redcap_import.UpsertRedcapRecordsByDateRangeBatchTest.test_all_records_synced
        """
        mock_get_records.return_value = [
            {"request_id": "case-001", "rf_test_requested": CaseType.CTTSO},
            {"request_id": "case-002", "rf_test_requested": CaseType.WGTS},
        ]

        result = upsert_redcap_records_by_date_range(after_date="2026-07-01 00:00:00")

        self.assertEqual(result, {"synced": 2, "failed": 0})
        self.assertEqual(Case.objects.count(), 2)

    @patch("app.service.redcap_import.get_redcap_record_by_date_range")
    def test_one_bad_record_does_not_abort_the_rest(self, mock_get_records):
        """
        One record with an unknown case type must not block the other records
        from being synced.

        python manage.py test app.tests.test_redcap_import.UpsertRedcapRecordsByDateRangeBatchTest.test_one_bad_record_does_not_abort_the_rest
        """
        mock_get_records.return_value = [
            {"request_id": "case-001", "rf_test_requested": "not_a_real_type"},
            {"request_id": "case-002", "rf_test_requested": CaseType.WGTS},
        ]

        result = upsert_redcap_records_by_date_range(after_date="2026-07-01 00:00:00")

        self.assertEqual(result, {"synced": 1, "failed": 1})
        self.assertFalse(Case.objects.filter(request_form_id="case-001").exists())
        self.assertTrue(Case.objects.filter(request_form_id="case-002").exists())

    @patch("app.service.redcap_import.get_redcap_record_by_date_range")
    def test_empty_record_list_writes_nothing(self, mock_get_records):
        """
        python manage.py test app.tests.test_redcap_import.UpsertRedcapRecordsByDateRangeBatchTest.test_empty_record_list_writes_nothing
        """
        mock_get_records.return_value = []

        result = upsert_redcap_records_by_date_range(after_date="2026-07-01 00:00:00")

        self.assertEqual(result, {"synced": 0, "failed": 0})
        self.assertEqual(Case.objects.count(), 0)


class UpsertCaseFromRedcapRecordIdempotencyTest(TestCase):
    """
    Re-syncing the same record must not create duplicate Cases or States.

    python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordIdempotencyTest
    """

    def setUp(self):
        self.record = {
            "request_id": "case-001",
            "rf_test_requested": CaseType.CTTSO,
            "cttso_receipt_date": "2026-07-01",
        }

    def test_syncing_twice_produces_one_case(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordIdempotencyTest.test_syncing_twice_produces_one_case
        """
        upsert_case_from_redcap_record(self.record)
        upsert_case_from_redcap_record(self.record)

        self.assertEqual(
            Case.objects.filter(request_form_id="case-001").count(), 1
        )

    def test_syncing_twice_produces_one_state_per_status(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordIdempotencyTest.test_syncing_twice_produces_one_state_per_status
        """
        case = upsert_case_from_redcap_record(self.record)
        upsert_case_from_redcap_record(self.record)

        self.assertEqual(
            State.objects.filter(
                case=case, status=CaseStatus.CTTSO_SAMPLE_RECEIVED
            ).count(),
            1,
        )
        self.assertEqual(
            State.objects.filter(
                case=case, status=CaseStatus.ALL_SAMPLE_RECEIVED
            ).count(),
            1,
        )

    def test_second_sync_updates_changed_field_not_recreate(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordIdempotencyTest.test_second_sync_updates_changed_field_not_recreate
        """
        upsert_case_from_redcap_record(self.record)

        updated_record = {**self.record, "nata_accred_report": "1"}
        case = upsert_case_from_redcap_record(updated_record)

        self.assertEqual(Case.objects.filter(request_form_id="case-001").count(), 1)
        self.assertTrue(case.is_nata_accredited)


class UpsertCaseFromRedcapRecordValidationTest(TestCase):
    """
    Invalid records must raise, not silently write bad data.

    python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordValidationTest
    """

    def test_missing_request_id_raises_key_error(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordValidationTest.test_missing_request_id_raises_key_error
        """
        with self.assertRaises(KeyError):
            upsert_case_from_redcap_record({"rf_test_requested": CaseType.CTTSO})

    def test_unknown_case_type_raises_value_error(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordValidationTest.test_unknown_case_type_raises_value_error
        """
        with self.assertRaises(ValueError):
            upsert_case_from_redcap_record(
                {"request_id": "case-001", "rf_test_requested": "bogus"}
            )

    def test_record_with_no_receipt_dates_creates_case_with_no_states(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordValidationTest.test_record_with_no_receipt_dates_creates_case_with_no_states
        """
        case = upsert_case_from_redcap_record(
            {"request_id": "case-001", "rf_test_requested": CaseType.CTTSO}
        )

        self.assertIsNotNone(case)
        self.assertEqual(State.objects.filter(case=case).count(), 0)


class UpsertCaseFromRedcapRecordDueDateTest(TestCase):
    """
    ALL_SAMPLE_RECEIVED state + due_date derivation per case type.

    python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordDueDateTest
    """

    def test_cttso_all_sample_received_sets_default_turnaround_due_date(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordDueDateTest.test_cttso_all_sample_received_sets_default_turnaround_due_date
        """
        receipt_date = date(2026, 7, 1)
        case = upsert_case_from_redcap_record(
            {
                "request_id": "case-001",
                "rf_test_requested": CaseType.CTTSO,
                "rf_study": "SomeOtherStudy",
                "cttso_receipt_date": receipt_date.isoformat(),
            }
        )

        self.assertTrue(
            State.objects.filter(
                case=case, status=CaseStatus.ALL_SAMPLE_RECEIVED
            ).exists()
        )
        self.assertEqual(
            case.due_date, receipt_date + timedelta(weeks=DEFAULT_TURNAROUND_WEEKS)
        )

    def test_short_turnaround_study_name_uses_shorter_due_date(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordDueDateTest.test_short_turnaround_study_name_uses_shorter_due_date
        """
        short_study_name = next(iter(SHORT_TURNAROUND_STUDY_NAMES))
        receipt_date = date(2026, 7, 1)
        case = upsert_case_from_redcap_record(
            {
                "request_id": "case-001",
                "rf_test_requested": CaseType.CTTSO,
                "rf_study": short_study_name,
                "cttso_receipt_date": receipt_date.isoformat(),
            }
        )

        self.assertEqual(
            case.due_date, receipt_date + timedelta(weeks=SHORT_TURNAROUND_WEEKS)
        )

    def test_wgts_case_needs_both_tumour_and_germline_dates(self):
        """
        Only the tumour sample date is present -> ALL_SAMPLE_RECEIVED must not
        fire yet for a WGTS case (it needs both tumour and germline).

        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordDueDateTest.test_wgts_case_needs_both_tumour_and_germline_dates
        """
        case = upsert_case_from_redcap_record(
            {
                "request_id": "case-001",
                "rf_test_requested": CaseType.WGTS,
                "tumour_receipt_date": "2026-07-01",
            }
        )

        self.assertFalse(
            State.objects.filter(
                case=case, status=CaseStatus.ALL_SAMPLE_RECEIVED
            ).exists()
        )
        self.assertIsNone(case.due_date)

    def test_due_date_already_set_is_not_overwritten(self):
        """
        python manage.py test app.tests.test_redcap_import.UpsertCaseFromRedcapRecordDueDateTest.test_due_date_already_set_is_not_overwritten
        """
        manual_due_date = date(2026, 1, 1)
        CaseFactory(
            request_form_id="case-001",
            type=CaseType.CTTSO,
            due_date=manual_due_date,
        )

        case = upsert_case_from_redcap_record(
            {
                "request_id": "case-001",
                "rf_test_requested": CaseType.CTTSO,
                "cttso_receipt_date": "2026-07-01",
            }
        )

        self.assertEqual(case.due_date, manual_due_date)
