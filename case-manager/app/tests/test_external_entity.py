"""
Tests for app.service.external_entity.resolve_pending_external_entities.

Behaviour under test
---------------------
For every queued PendingExternalEntity of type "sample":
  1. The sample (and its libraries) are always resolved via
     get_or_create_entities_by_sample_id() -- this is called even when a matching
     ExternalEntity already exists locally, because an existing entity may not yet
     be linked to *this* pending row's case.
  2. Every entity returned (sample + libraries) is linked to the pending row's case
     via a confirmed CaseExternalEntityLink (idempotent get_or_create).
  3. If at least one link was made, the PendingExternalEntity row is deleted and
     counted as "resolved".
  4. If nothing could be resolved, the row is left queued and counted as
     "still_pending".
  5. Rows whose type is not "sample" are left untouched and counted as "skipped".
  6. Rows that raise during processing (e.g. a blocked/terminal case) are left
     queued, logged, and counted as "failed" -- without aborting other rows.

python manage.py test app.tests.test_external_entity
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from app.models import CaseExternalEntityLink, ExternalEntity, PendingExternalEntity
from app.models.case import CaseType
from app.models.state import CaseStatus
from app.service.external_entity import resolve_pending_external_entities
from app.tests.factories import (
    CASE_REQUEST_FORM_ID_001,
    CASE_REQUEST_FORM_ID_002,
    CaseFactory,
    StateFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cttso_case(**kwargs):
    return CaseFactory(type=CaseType.CTTSO, **kwargs)


def _make_external_entity(alias: str, entity_type: str = "sample") -> ExternalEntity:
    """Create a pre-existing resolved ExternalEntity for a sample/library alias."""
    return ExternalEntity.objects.create(
        service_name="metadata",
        type=entity_type,
        alias=alias,
    )


def _make_pending(case, alias, type_="sample", service_name="metadata"):
    return PendingExternalEntity.objects.create(
        case=case,
        service_name=service_name,
        type=type_,
        alias=alias,
    )


class ResolvePendingExternalEntitiesTest(TestCase):
    """
    python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest
    """

    def setUp(self):
        patcher = patch(
            "app.service.external_entity.get_or_create_entities_by_sample_id"
        )
        self.mock_lookup = patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_queue_returns_all_zero_summary(self):
        """
        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_empty_queue_returns_all_zero_summary
        """
        self.assertEqual(PendingExternalEntity.objects.count(), 0)

        result = resolve_pending_external_entities()

        self.assertEqual(
            result,
            {
                "resolved": 0,
                "still_pending": 0,
                "skipped": 0,
                "failed": 0,
            },
        )
        self.mock_lookup.assert_not_called()

    def test_non_sample_type_is_skipped_and_not_looked_up(self):
        """
        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_non_sample_type_is_skipped_and_not_looked_up
        """
        case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        pending = _make_pending(case, "WFR001", type_="workflowrun")

        result = resolve_pending_external_entities()

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["still_pending"], 0)
        self.assertEqual(result["failed"], 0)
        self.mock_lookup.assert_not_called()
        self.assertTrue(
            PendingExternalEntity.objects.filter(orcabus_id=pending.orcabus_id).exists()
        )

    def test_metadata_lookup_is_always_called_even_if_entity_already_resolved(self):
        """
        A sample whose ExternalEntity already exists locally must still be resolved
        via get_or_create_entities_by_sample_id -- the existing entity may not yet be
        linked to this pending row's case (e.g. created via a different case/race).

        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_metadata_lookup_is_always_called_even_if_entity_already_resolved
        """
        case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        alias = "SMP-EXISTING"
        existing_entity = _make_external_entity(alias)
        pending = _make_pending(case, alias)

        self.mock_lookup.return_value = (existing_entity, [])

        result = resolve_pending_external_entities()

        self.mock_lookup.assert_called_once_with(alias)
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["still_pending"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertFalse(
            PendingExternalEntity.objects.filter(orcabus_id=pending.orcabus_id).exists()
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=case, external_entity=existing_entity
            ).exists()
        )

    def test_already_linked_case_is_idempotent_and_row_still_deleted(self):
        """
        If the CaseExternalEntityLink already exists (e.g. from a previous run),
        get_or_create must not error, and the pending row is still deleted.

        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_already_linked_case_is_idempotent_and_row_still_deleted
        """
        case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        alias = "SMP-IDEMPOTENT"
        external_entity = _make_external_entity(alias)
        CaseExternalEntityLink.objects.get_or_create(
            case=case, external_entity=external_entity
        )
        pending = _make_pending(case, alias)

        self.mock_lookup.return_value = (external_entity, [])

        result = resolve_pending_external_entities()

        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["still_pending"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertFalse(
            PendingExternalEntity.objects.filter(orcabus_id=pending.orcabus_id).exists()
        )
        self.assertEqual(
            CaseExternalEntityLink.objects.filter(
                case=case, external_entity=external_entity
            ).count(),
            1,
        )

    def test_resolves_sample_and_links_all_libraries(self):
        """
        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_resolves_sample_and_links_all_libraries
        """
        case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        alias = "SMP-MULTI-LIB"
        pending = _make_pending(case, alias)

        sample_entity = _make_external_entity(alias)
        library_1 = _make_external_entity("LIB001", entity_type="library")
        library_2 = _make_external_entity("LIB002", entity_type="library")
        self.mock_lookup.return_value = (sample_entity, [library_1, library_2])

        result = resolve_pending_external_entities()

        self.assertEqual(result["resolved"], 1)
        self.assertFalse(
            PendingExternalEntity.objects.filter(orcabus_id=pending.orcabus_id).exists()
        )
        self.assertEqual(CaseExternalEntityLink.objects.filter(case=case).count(), 3)

    def test_unresolvable_row_left_queued_as_still_pending(self):
        """
        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_unresolvable_row_left_queued_as_still_pending
        """
        case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        alias = "SMP-UNRESOLVED"
        pending = _make_pending(case, alias)

        self.mock_lookup.return_value = (None, [])

        result = resolve_pending_external_entities()

        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["still_pending"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertTrue(
            PendingExternalEntity.objects.filter(orcabus_id=pending.orcabus_id).exists()
        )
        self.assertEqual(CaseExternalEntityLink.objects.filter(case=case).count(), 0)

    def test_blocked_case_fails_row_but_other_row_still_resolved(self):
        """
        A pending row whose case is in a terminal state (e.g. COMPLETED) must
        raise ValidationError from CaseExternalEntityLink.save(), be caught,
        counted as failed, and retained -- while an unrelated resolvable row
        in the same run is still linked and deleted.

        python manage.py test app.tests.test_external_entity.ResolvePendingExternalEntitiesTest.test_blocked_case_fails_row_but_other_row_still_resolved
        """
        user = UserFactory(name="Alice")

        # Blocked case: latest state is COMPLETED (a terminal status).
        blocked_case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_001)
        StateFactory(
            case=blocked_case,
            status=CaseStatus.COMPLETED,
            created_by=user,
            event_date=date(2024, 1, 1),
        )
        blocked_alias = "SMP-BLOCKED"
        blocked_entity = _make_external_entity(blocked_alias)
        blocked_pending = _make_pending(blocked_case, blocked_alias)

        # Unrelated, resolvable row on a different (non-blocked) case.
        ok_case = _cttso_case(request_form_id=CASE_REQUEST_FORM_ID_002)
        ok_alias = "SMP-OK"
        ok_entity = _make_external_entity(ok_alias)
        ok_pending = _make_pending(ok_case, ok_alias)

        def _side_effect(alias):
            if alias == blocked_alias:
                return blocked_entity, []
            return ok_entity, []

        self.mock_lookup.side_effect = _side_effect

        result = resolve_pending_external_entities()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["still_pending"], 0)
        self.assertEqual(result["skipped"], 0)

        # Blocked row retained, no link created.
        self.assertTrue(
            PendingExternalEntity.objects.filter(
                orcabus_id=blocked_pending.orcabus_id
            ).exists()
        )
        self.assertFalse(
            CaseExternalEntityLink.objects.filter(case=blocked_case).exists()
        )

        # Unrelated row resolved and deleted.
        self.assertFalse(
            PendingExternalEntity.objects.filter(
                orcabus_id=ok_pending.orcabus_id
            ).exists()
        )
        self.assertTrue(
            CaseExternalEntityLink.objects.filter(
                case=ok_case, external_entity=ok_entity
            ).exists()
        )
