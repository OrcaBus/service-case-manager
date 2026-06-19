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

python manage.py test app.tests.test_redcap_import
"""

from django.test import TestCase

from app.models import CaseExternalEntityLink, ExternalEntity, PendingExternalEntity
from app.models.case import CaseType
from app.service.redcap_import import resolve_sample_links_from_redcap_record
from app.tests.factories import (
    CaseFactory,
    CASE_REQUEST_FORM_ID_001,
    CASE_REQUEST_FORM_ID_002,
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
    When no ExternalEntity exists for a sample alias a PendingExternalEntity
    must be created and no CaseExternalEntityLink may be created.

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

    def test_same_alias_in_two_cases_creates_independent_pending_rows(self):
        """
        python manage.py test app.tests.test_redcap_import.ResolveSampleLinksEdgeCasesTest.test_same_alias_in_two_cases_creates_independent_pending_rows
        The updated unique_together includes `case`, so the same alias can be
        queued separately for two different cases.
        """
        case_a = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        case_b = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_002)
        record = {"cttso_sample_id": "SHARED-ALIAS"}

        resolve_sample_links_from_redcap_record(case_a, record)
        resolve_sample_links_from_redcap_record(case_b, record)

        self.assertEqual(
            PendingExternalEntity.objects.filter(alias="SHARED-ALIAS").count(), 2
        )
