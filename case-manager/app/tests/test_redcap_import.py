"""
Tests for app.service.redcap_import.resolve_sample_links_from_redcap_record.

Behaviour under test
---------------------
For each sample ID found in a REDCap record the function must:
  1. If a matching ExternalEntity (service_name="metadata", type="sample", alias=<id>)
     already exists → create a confirmed CaseExternalEntityLink and NO PendingExternalEntity.
  2. If no such ExternalEntity exists → create a PendingExternalEntity and NO
     CaseExternalEntityLink.
  3. Both paths are idempotent (calling twice produces exactly one row, not two).
  4. Blank / missing sample IDs are silently skipped.
  5. A case type with no defined field mapping returns immediately with no DB writes.

Tests for app.service.redcap_import sync functions:
  - upsert_redcap_records_by_date_range (batch fetch + upsert)
  - upsert_case_from_redcap_record (single record -> Case/State/due_date logic)

python manage.py test app.tests.test_redcap_import
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from app.models import (
    Case,
    CaseExternalEntityLink,
    ExternalEntity,
    PendingExternalEntity,
    State,
)
from app.models.case import CaseType, CaseStudyType
from app.models.state import CaseStatus
from app.service.redcap_import import (
    DEFAULT_TURNAROUND_WEEKS,
    SHORT_TURNAROUND_STUDY_NAMES,
    SHORT_TURNAROUND_WEEKS,
    resolve_sample_links_from_redcap_record,
    upsert_case_from_redcap_record,
    upsert_redcap_records_by_date_range,
)
from app.tests.factories import (
    CASE_REQUEST_FORM_ID_001,
    CASE_REQUEST_FORM_ID_002,
    CaseFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wgts_case(**kwargs):
    return CaseFactory(type=CaseType.WGTS, **kwargs)


def _cttso_case(**kwargs):
    return CaseFactory(type=CaseType.CTTSO, **kwargs)


def _make_external_entity(alias: str) -> ExternalEntity:
    """Create a pre-existing resolved ExternalEntity for a sample alias."""
    return ExternalEntity.objects.create(
        service_name="metadata",
        type="sample",
        alias=alias,
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class ResolveSampleLinksNoExternalEntityTest(TestCase):
    """
    When no ExternalEntity exists for a sample alias, and the metadata service
    also has no matching sample, a PendingExternalEntity must be created and no
    CaseExternalEntityLink may be created.

    python manage.py test app.tests.test_redcap_import.ResolveSampleLinksNoExternalEntityTest
    """

    def setUp(self):
        self.case = _wgts_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        self.record = {
            "request_id": CASE_REQUEST_FORM_ID_001,
            "rf_test_requested": CaseType.WGTS,
            "tumour_sample_id": "SBJ001-T",
            "germline_sample_id": "SBJ001-G",
            "wts_sample_id": "",  # intentionally blank
        }
        # Metadata service has no matching sample for either alias in this test.
        patcher = patch("app.service.redcap_import.get_or_create_entities_by_sample_id")
        self.mock_lookup = patcher.start()
        self.mock_lookup.return_value = (None, [])
        self.addCleanup(patcher.stop)

    def test_creates_pending_for_each_non_empty_sample(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksNoExternalEntityTest.test_creates_pending_for_each_non_empty_sample
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)

        # One pending per non-blank sample field
        pending = PendingExternalEntity.objects.filter(case=self.case)
        self.assertEqual(pending.count(), 2)
        aliases = set(pending.values_list("alias", flat=True))
        self.assertSetEqual(aliases, {"SBJ001-T", "SBJ001-G"})

    def test_no_confirmed_link_created(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksNoExternalEntityTest.test_no_confirmed_link_created
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        self.assertEqual(
            CaseExternalEntityLink.objects.filter(case=self.case).count(), 0
        )

    def test_idempotent_calling_twice_produces_one_pending_row(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksNoExternalEntityTest.test_idempotent_calling_twice_produces_one_pending_row
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.assertEqual(
            PendingExternalEntity.objects.filter(case=self.case).count(), 2
        )


class ResolveSampleLinksExternalEntityExistsTest(TestCase):
    """
    When an ExternalEntity already exists for a sample alias a
    CaseExternalEntityLink must be created and no PendingExternalEntity may be
    created for that alias.

    python manage.py test app.tests.test_redcap_import.ResolveSampleLinksExternalEntityExistsTest
    """

    def setUp(self):
        self.case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        self.sample_alias = "LIB001"
        self.external_entity = _make_external_entity(self.sample_alias)
        self.record = {
            "request_id": CASE_REQUEST_FORM_ID_001,
            "rf_test_requested": CaseType.CTTSO,
            "cttso_sample_id": self.sample_alias,
        }

    def test_creates_confirmed_link(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksExternalEntityExistsTest.test_creates_confirmed_link
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)

        links = CaseExternalEntityLink.objects.filter(
            case=self.case, external_entity=self.external_entity
        )
        self.assertEqual(links.count(), 1)

    def test_no_pending_entity_created(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksExternalEntityExistsTest.test_no_pending_entity_created
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        self.assertEqual(
            PendingExternalEntity.objects.filter(case=self.case).count(), 0
        )

    def test_idempotent_calling_twice_produces_one_link(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksExternalEntityExistsTest.test_idempotent_calling_twice_produces_one_link
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.assertEqual(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=self.external_entity
            ).count(),
            1,
        )


class ResolveSampleLinksMixedTest(TestCase):
    """
    WGTS case where one sample already has an ExternalEntity and another does not.
    The resolved one gets a CaseExternalEntityLink; the unresolved one gets a
    PendingExternalEntity.

    python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMixedTest
    """

    def setUp(self):
        self.case = _wgts_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        self.resolved_alias = "SBJ001-T"
        self.unresolved_alias = "SBJ001-G"
        self.external_entity = _make_external_entity(self.resolved_alias)
        self.record = {
            "request_id": CASE_REQUEST_FORM_ID_001,
            "rf_test_requested": CaseType.WGTS,
            "tumour_sample_id": self.resolved_alias,
            "germline_sample_id": self.unresolved_alias,
            "wts_sample_id": "",
        }
        # Metadata service has no match for the unresolved alias in this test.
        patcher = patch("app.service.redcap_import.get_or_create_entities_by_sample_id")
        self.mock_lookup = patcher.start()
        self.mock_lookup.return_value = (None, [])
        self.addCleanup(patcher.stop)

    def test_confirmed_link_for_resolved_alias(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMixedTest.test_confirmed_link_for_resolved_alias
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        self.assertEqual(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=self.external_entity
            ).count(),
            1,
        )

    def test_pending_for_unresolved_alias(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMixedTest.test_pending_for_unresolved_alias
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        self.assertEqual(
            PendingExternalEntity.objects.filter(
                case=self.case, alias=self.unresolved_alias
            ).count(),
            1,
        )

    def test_no_pending_for_resolved_alias(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMixedTest.test_no_pending_for_resolved_alias
        """
        resolve_sample_links_from_redcap_record(self.case, self.record)
        self.assertEqual(
            PendingExternalEntity.objects.filter(
                case=self.case, alias=self.resolved_alias
            ).count(),
            0,
        )


class ResolveSampleLinksEdgeCasesTest(TestCase):
    """
    Edge cases: blank IDs, whitespace-only IDs, unknown case type.

    python manage.py test app.tests.test_redcap_import.ResolveSampleLinksEdgeCasesTest
    """

    def test_blank_sample_ids_are_skipped(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksEdgeCasesTest.test_blank_sample_ids_are_skipped
        """
        case = _wgts_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        record = {
            "tumour_sample_id": "",
            "germline_sample_id": "   ",  # whitespace only
            "wts_sample_id": None,
        }
        resolve_sample_links_from_redcap_record(case, record)

        self.assertEqual(PendingExternalEntity.objects.filter(case=case).count(), 0)
        self.assertEqual(CaseExternalEntityLink.objects.filter(case=case).count(), 0)

    def test_unknown_case_type_produces_no_writes(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksEdgeCasesTest.test_unknown_case_type_produces_no_writes
        A case type with no sample field mapping (e.g. wgs_n) must exit early.
        """
        case = CaseFactory(
            request_form_id=CASE_REQUEST_FORM_ID_002,
            type=CaseType.WGS_N,
        )
        record = {"some_sample_id": "SBJ999"}
        resolve_sample_links_from_redcap_record(case, record)

        self.assertEqual(PendingExternalEntity.objects.filter(case=case).count(), 0)
        self.assertEqual(CaseExternalEntityLink.objects.filter(case=case).count(), 0)

    def test_same_alias_in_two_cases_raises_integrity_error(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksEdgeCasesTest.test_same_alias_in_two_cases_raises_integrity_error

        NOTE: PendingExternalEntity.unique_together is currently
        ("alias", "type", "service_name") — it does NOT include `case`
        (see app/migrations/0005_..., which set unique_together to that
        exact tuple). So queuing the same alias for a second case raises an
        IntegrityError rather than creating an independent row. This is a
        pre-existing model/behaviour gap unrelated to the metadata-lookup
        feature — flagged here rather than silently asserting incorrect
        "independent rows per case" behaviour.
        """
        case_a = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        case_b = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_002)
        record = {"cttso_sample_id": "SHARED-ALIAS"}

        with patch(
            "app.service.redcap_import.get_or_create_entities_by_sample_id"
        ) as mock_lookup:
            mock_lookup.return_value = (None, [])
            resolve_sample_links_from_redcap_record(case_a, record)

            with self.assertRaises(IntegrityError):
                resolve_sample_links_from_redcap_record(case_b, record)


class ResolveSampleLinksMetadataLookupTest(TestCase):
    """
    New behaviour: when no local ExternalEntity matches the alias, the metadata
    service is queried via get_or_create_entities_by_sample_id *before* falling
    back to a PendingExternalEntity.
      - If it resolves a sample and/or library entities, confirmed
        CaseExternalEntityLink rows are created for all of them and NO
        PendingExternalEntity is created.
      - If it resolves nothing, a PendingExternalEntity is queued (unchanged
        fallback behaviour).
      - If a local ExternalEntity already exists, the metadata lookup must be
        skipped entirely (fast path).

    python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest
    """

    def setUp(self):
        self.case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        self.sample_alias = "SMP001"
        self.record = {
            "request_id": CASE_REQUEST_FORM_ID_001,
            "rf_test_requested": CaseType.CTTSO,
            "cttso_sample_id": self.sample_alias,
        }
        patcher = patch("app.service.redcap_import.get_or_create_entities_by_sample_id")
        self.mock_lookup = patcher.start()
        self.addCleanup(patcher.stop)

    def test_metadata_resolves_sample_and_library_creates_confirmed_links(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest.test_metadata_resolves_sample_and_library_creates_confirmed_links
        """

        # Entities are created *inside* the mocked call — simulating them being
        # created by get_or_create_entities_by_sample_id when it queries the
        # metadata service — so the local DB "fast path" filter genuinely finds
        # nothing beforehand and the mocked lookup path is exercised for real.
        def _side_effect(sample_id):
            sample_entity = ExternalEntity.objects.create(
                service_name="metadata", type="sample", alias=sample_id
            )
            library_entity = ExternalEntity.objects.create(
                service_name="metadata", type="library", alias="LIB001"
            )
            return sample_entity, [library_entity]

        self.mock_lookup.side_effect = _side_effect

        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.mock_lookup.assert_called_once_with(self.sample_alias)
        sample_entity = ExternalEntity.objects.get(
            alias=self.sample_alias, type="sample"
        )
        library_entity = ExternalEntity.objects.get(alias="LIB001", type="library")
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=sample_entity
            ).exists()
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=library_entity
            ).exists()
        )
        self.assertEqual(
            PendingExternalEntity.objects.filter(case=self.case).count(), 0
        )

    def test_metadata_resolves_multiple_libraries_links_all(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest.test_metadata_resolves_multiple_libraries_links_all
        """

        def _side_effect(sample_id):
            sample_entity = ExternalEntity.objects.create(
                service_name="metadata", type="sample", alias=sample_id
            )
            library_1 = ExternalEntity.objects.create(
                service_name="metadata", type="library", alias="LIB001"
            )
            library_2 = ExternalEntity.objects.create(
                service_name="metadata", type="library", alias="LIB002"
            )
            return sample_entity, [library_1, library_2]

        self.mock_lookup.side_effect = _side_effect

        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.assertEqual(
            CaseExternalEntityLink.objects.filter(case=self.case).count(), 3
        )

    def test_metadata_resolves_only_sample_no_library_still_confirmed(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest.test_metadata_resolves_only_sample_no_library_still_confirmed
        """

        def _side_effect(sample_id):
            sample_entity = ExternalEntity.objects.create(
                service_name="metadata", type="sample", alias=sample_id
            )
            return sample_entity, []

        self.mock_lookup.side_effect = _side_effect

        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.mock_lookup.assert_called_once_with(self.sample_alias)
        sample_entity = ExternalEntity.objects.get(
            alias=self.sample_alias, type="sample"
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=sample_entity
            ).exists()
        )
        self.assertEqual(
            PendingExternalEntity.objects.filter(case=self.case).count(), 0
        )

    def test_metadata_resolves_nothing_queues_pending(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest.test_metadata_resolves_nothing_queues_pending
        """
        self.mock_lookup.return_value = (None, [])

        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.mock_lookup.assert_called_once_with(self.sample_alias)
        self.assertTrue(
            PendingExternalEntity.objects.filter(
                case=self.case,
                alias=self.sample_alias,
                type="sample",
                service_name="metadata",
            ).exists()
        )
        self.assertEqual(
            CaseExternalEntityLink.objects.filter(case=self.case).count(), 0
        )

    def test_idempotent_calling_twice_does_not_duplicate_links(self):
        """
        Second call finds the sample ExternalEntity created by the first call via
        the local DB fast path, so the mocked metadata lookup is only invoked once.

        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest.test_idempotent_calling_twice_does_not_duplicate_links
        """

        def _side_effect(sample_id):
            sample_entity = ExternalEntity.objects.create(
                service_name="metadata", type="sample", alias=sample_id
            )
            library_entity = ExternalEntity.objects.create(
                service_name="metadata", type="library", alias="LIB001"
            )
            return sample_entity, [library_entity]

        self.mock_lookup.side_effect = _side_effect

        resolve_sample_links_from_redcap_record(self.case, self.record)
        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.mock_lookup.assert_called_once_with(self.sample_alias)
        sample_entity = ExternalEntity.objects.get(
            alias=self.sample_alias, type="sample"
        )
        library_entity = ExternalEntity.objects.get(alias="LIB001", type="library")
        self.assertEqual(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=sample_entity
            ).count(),
            1,
        )
        self.assertEqual(
            CaseExternalEntityLink.objects.filter(
                case=self.case, external_entity=library_entity
            ).count(),
            1,
        )

    def test_existing_external_entity_short_circuits_metadata_lookup(self):
        """
        If a matching ExternalEntity already exists locally, the metadata
        service must NOT be queried at all (fast DB path takes precedence).

        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksMetadataLookupTest.test_existing_external_entity_short_circuits_metadata_lookup
        """
        _make_external_entity(self.sample_alias)

        resolve_sample_links_from_redcap_record(self.case, self.record)

        self.mock_lookup.assert_not_called()


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

        self.assertEqual(Case.objects.filter(request_form_id="case-001").count(), 1)

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
