"""
Integration tests for workflow_run_draft_publisher Lambda handler.

These tests verify the handler's core functionality:
- Case discovery via linked libraries (sequence_run_linking-style event)
- Case type filtering (only cttso cases processed)
- Workflow run deduplication (skip if workflow_run exists)
- Library entity retrieval and validation
- Event publishing to EventBridge
"""

import os
from unittest.mock import patch, Mock
import django

# Initialize Django for tests
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from handler.workflow_run_draft_publisher import handler


def _make_case_lookup_link(case):
    """Build a mock CaseExternalEntityLink returned by the library-alias lookup."""
    link = Mock()
    link.case = case
    return link


def _make_filter_side_effect(
    case_lookup_links=None,
    workflow_run_links=None,
    library_links=None,
):
    """
    Build a side_effect function for CaseExternalEntityLink.objects.filter that
    dispatches to the correct mocked queryset based on the filter kwargs used by
    the handler:

    1. filter(external_entity__alias=..., external_entity__type="library")
       -> .select_related("case") -> iterable of links with `.case`
    2. filter(case=..., external_entity__type="workflow_run", external_entity__prefix="wfr")
       -> .select_related("external_entity") -> iterable of links with `.external_entity`
    3. filter(case=..., external_entity__type="library", external_entity__service_name="metadata")
       -> .select_related("external_entity") -> queryset with `.exists()` / iterable
    """
    case_lookup_links = case_lookup_links or []
    workflow_run_links = workflow_run_links or []
    library_links = library_links or []

    def filter_side_effect(*args, **kwargs):
        mock_qs = Mock()

        if "external_entity__alias" in kwargs:
            related_qs = Mock()
            related_qs.__iter__ = Mock(return_value=iter(case_lookup_links))
            mock_qs.select_related.return_value = related_qs
            return mock_qs

        if kwargs.get("external_entity__type") == "workflow_run":
            related_qs = Mock()
            related_qs.__iter__ = Mock(return_value=iter(workflow_run_links))
            mock_qs.select_related.return_value = related_qs
            return mock_qs

        if kwargs.get("external_entity__type") == "library":
            related_qs = Mock()
            related_qs.exists.return_value = len(library_links) > 0
            related_qs.__iter__ = Mock(return_value=iter(library_links))
            mock_qs.select_related.return_value = related_qs
            return mock_qs

        mock_qs.select_related.return_value = Mock()
        return mock_qs

    return filter_side_effect


def test_handler_skips_event_with_no_linked_libraries():
    """Handler skips events without 'linkedLibraries' in detail."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
    ):
        event = {"detail": {"instrumentRunId": "run1", "sequenceRunId": "r.xxx"}}
        handler(event, None)

        mock_link_model.objects.filter.assert_not_called()
        mock_emit.assert_not_called()


def test_handler_skips_when_no_case_found_for_libraries():
    """Handler skips when no case is linked to any of the given libraries."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
    ):
        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[]
        )

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001", "L2400002"],
            }
        }
        handler(event, None)

        mock_emit.assert_not_called()


def test_handler_skips_non_cttso_case():
    """Handler skips cases with type != 'cttso'."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="wgts")

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
        )

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }
        handler(event, None)

        mock_emit.assert_not_called()


def test_handler_skips_case_with_existing_cttso_workflow_run():
    """Handler skips cases that already have a matching CTTSO_WORKFLOW_NAME workflow_run linked."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch(
            "handler.workflow_run_draft_publisher.fetch_external_entity_data"
        ) as mock_fetch,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_workflow_run_entity = Mock(
            orcabus_id="wfr.existing123", alias="20240101abc12345"
        )
        mock_workflow_run_link = Mock(external_entity=mock_workflow_run_entity)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            workflow_run_links=[mock_workflow_run_link],
        )
        # The linked workflow_run resolves (via the Workflow Service) to the same
        # workflow this handler drafts, so it should count as a dedup match.
        mock_fetch.return_value = (
            "workflow",
            {"workflow": {"name": "dragen-tso500-ctdna"}},
        )

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }
        handler(event, None)

        mock_emit.assert_not_called()


def test_handler_does_not_skip_case_with_unrelated_workflow_run():
    """
    Handler does NOT skip a case whose only existing workflow_run link resolves
    to a different workflow (not CTTSO_WORKFLOW_NAME) — dedup must be scoped to
    the specific cttso workflow, not "any workflow_run exists".
    """
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch(
            "handler.workflow_run_draft_publisher.fetch_external_entity_data"
        ) as mock_fetch,
        patch(
            "handler.workflow_run_draft_publisher.build_workflow_run_draft"
        ) as mock_builder,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
        patch("handler.workflow_run_draft_publisher.WorkflowRunUpdate") as mock_wru,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_unrelated_workflow_run_entity = Mock(
            orcabus_id="wfr.unrelated123", alias="20240101unrelated"
        )
        mock_unrelated_workflow_run_link = Mock(
            external_entity=mock_unrelated_workflow_run_entity
        )

        mock_library_entity = Mock(orcabus_id="lib.lib001", alias="L2400001")
        mock_library_link = Mock(external_entity=mock_library_entity)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            workflow_run_links=[mock_unrelated_workflow_run_link],
            library_links=[mock_library_link],
        )
        mock_fetch.return_value = (
            "workflow",
            {"workflow": {"name": "some-other-workflow"}},
        )

        mock_builder.return_value = {
            "status": "DRAFT",
            "portalRunId": "20240120abc12345",
            "workflowRunName": "name",
            "workflow": {
                "orcabusId": "wfl.test123",
                "name": "dragen-tso500-ctdna",
                "version": "4.3.6",
                "codeVersion": "1.0.0",
                "executionEngine": "nextflow",
                "executionEnginePipelineId": "umccr/dragen-tso500",
                "validationState": "validated",
            },
            "libraries": [],
        }
        mock_wru.return_value = Mock(portalRunId="20240120abc12345")

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }
        handler(event, None)

        mock_builder.assert_called_once()
        mock_emit.assert_called_once()


def test_handler_continues_dedup_check_when_workflow_run_not_found():
    """
    If a linked workflow_run can no longer be resolved from the Workflow Service
    (Http404), the dedup check logs a warning and continues rather than raising.
    """
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch(
            "handler.workflow_run_draft_publisher.fetch_external_entity_data"
        ) as mock_fetch,
        patch(
            "handler.workflow_run_draft_publisher.build_workflow_run_draft"
        ) as mock_builder,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
        patch("handler.workflow_run_draft_publisher.WorkflowRunUpdate") as mock_wru,
    ):
        from django.http import Http404

        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_stale_workflow_run_entity = Mock(
            orcabus_id="wfr.stale123", alias="20240101stale"
        )
        mock_stale_workflow_run_link = Mock(
            external_entity=mock_stale_workflow_run_entity
        )

        mock_library_entity = Mock(orcabus_id="lib.lib001", alias="L2400001")
        mock_library_link = Mock(external_entity=mock_library_entity)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            workflow_run_links=[mock_stale_workflow_run_link],
            library_links=[mock_library_link],
        )
        mock_fetch.side_effect = Http404("not found")

        mock_builder.return_value = {
            "status": "DRAFT",
            "portalRunId": "20240120abc12345",
            "workflowRunName": "name",
            "workflow": {
                "orcabusId": "wfl.test123",
                "name": "dragen-tso500-ctdna",
                "version": "4.3.6",
                "codeVersion": "1.0.0",
                "executionEngine": "nextflow",
                "executionEnginePipelineId": "umccr/dragen-tso500",
                "validationState": "validated",
            },
            "libraries": [],
        }
        mock_wru.return_value = Mock(portalRunId="20240120abc12345")

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }
        handler(event, None)

        mock_builder.assert_called_once()
        mock_emit.assert_called_once()


def test_handler_skips_case_with_no_libraries():
    """Handler skips cases with no library entities."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            library_links=[],
        )

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }
        handler(event, None)

        mock_emit.assert_not_called()


def test_handler_raises_error_for_library_missing_orcabus_id():
    """Handler raises ValueError when library entity is missing orcabus_id."""
    with patch(
        "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
    ) as mock_link_model:
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_library_entity = Mock(orcabus_id=None, alias="L2400001")
        mock_library_link = Mock(external_entity=mock_library_entity)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            library_links=[mock_library_link],
        )

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }

        try:
            handler(event, None)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "missing orcabus_id" in str(e)


def test_handler_raises_error_for_library_missing_alias():
    """Handler raises ValueError when library entity is missing alias."""
    with patch(
        "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
    ) as mock_link_model:
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_library_entity = Mock(orcabus_id="lib.lib001", alias=None)
        mock_library_link = Mock(external_entity=mock_library_entity)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            library_links=[mock_library_link],
        )

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }

        try:
            handler(event, None)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "missing alias" in str(e)


def test_handler_success_with_valid_cttso_case():
    """
    Successful handler execution with valid cttso case found via linked libraries.

    Verifies that:
    - Case is discovered via the library alias link
    - Case type is checked
    - Deduplication check is performed
    - Library entities are retrieved
    - Library validation passes
    - Draft builder is called
    - Event is emitted to EventBridge
    """
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch(
            "handler.workflow_run_draft_publisher.build_workflow_run_draft"
        ) as mock_builder,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
        patch(
            "handler.workflow_run_draft_publisher.WorkflowRunUpdate"
        ) as mock_workflow_run_update,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_library_entity1 = Mock(orcabus_id="lib.lib001", alias="L2400001")
        mock_library_entity2 = Mock(orcabus_id="lib.lib002", alias="L2400002")
        mock_library_link1 = Mock(external_entity=mock_library_entity1)
        mock_library_link2 = Mock(external_entity=mock_library_entity2)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            library_links=[mock_library_link1, mock_library_link2],
        )

        mock_draft_dict = {
            "status": "DRAFT",
            "portalRunId": "20240120abc12345",
            "workflowRunName": "umccr--automated--dragen-tso500-ctdna--4-3-6--20240120abc12345",
            "workflow": {
                "orcabusId": "wfl.test123",
                "name": "dragen-tso500-ctdna",
                "version": "4.3.6",
                "codeVersion": "1.0.0",
                "executionEngine": "nextflow",
                "executionEnginePipelineId": "umccr/dragen-tso500",
                "validationState": "validated",
            },
            "libraries": [
                {
                    "orcabusId": "lib.lib001",
                    "libraryId": "L2400001",
                    "readsets": [
                        {"orcabusId": "rds.001", "rgid": "1.ACGT.240101_RUN001"}
                    ],
                }
            ],
        }
        mock_builder.return_value = mock_draft_dict

        mock_workflow_run_model = Mock(portalRunId="20240120abc12345")
        mock_workflow_run_update.return_value = mock_workflow_run_model

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001", "L2400002"],
            }
        }
        handler(event, None)

        mock_builder.assert_called_once()
        call_args = mock_builder.call_args
        assert call_args[0][0] == mock_case
        assert len(call_args[0][1]) == 2
        assert mock_library_entity1 in call_args[0][1]
        assert mock_library_entity2 in call_args[0][1]

        mock_workflow_run_update.assert_called_once_with(**mock_draft_dict)

        mock_emit.assert_called_once_with(
            detail_type="WorkflowRunDraft", event_detail_model=mock_workflow_run_model
        )


def test_handler_propagates_builder_exception():
    """Handler propagates exceptions from draft builder for Lambda retry."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch(
            "handler.workflow_run_draft_publisher.build_workflow_run_draft"
        ) as mock_builder,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_library_entity = Mock(orcabus_id="lib.lib001", alias="L2400001")
        mock_library_link = Mock(external_entity=mock_library_entity)

        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[_make_case_lookup_link(mock_case)],
            library_links=[mock_library_link],
        )

        mock_builder.side_effect = RuntimeError("Workflow service unavailable")

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001"],
            }
        }

        try:
            handler(event, None)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Workflow service unavailable" in str(e)


def test_handler_deduplicates_cases_across_libraries():
    """When multiple linked libraries resolve to the same case, only process it once."""
    with (
        patch(
            "handler.workflow_run_draft_publisher.CaseExternalEntityLink"
        ) as mock_link_model,
        patch(
            "handler.workflow_run_draft_publisher.build_workflow_run_draft"
        ) as mock_builder,
        patch("handler.workflow_run_draft_publisher.emit_event") as mock_emit,
        patch("handler.workflow_run_draft_publisher.WorkflowRunUpdate") as mock_wru,
    ):
        mock_case = Mock(orcabus_id="cas.test123", type="cttso")

        mock_library_entity = Mock(orcabus_id="lib.lib001", alias="L2400001")
        mock_library_link = Mock(external_entity=mock_library_entity)

        # Both linked libraries resolve to the same case
        mock_link_model.objects.filter.side_effect = _make_filter_side_effect(
            case_lookup_links=[
                _make_case_lookup_link(mock_case),
                _make_case_lookup_link(mock_case),
            ],
            library_links=[mock_library_link],
        )

        mock_builder.return_value = {
            "status": "DRAFT",
            "portalRunId": "20240120abc12345",
            "workflowRunName": "name",
            "workflow": {
                "orcabusId": "wfl.test123",
                "name": "dragen-tso500-ctdna",
                "version": "4.3.6",
                "codeVersion": "1.0.0",
                "executionEngine": "nextflow",
                "executionEnginePipelineId": "umccr/dragen-tso500",
                "validationState": "validated",
            },
            "libraries": [],
        }
        mock_wru.return_value = Mock(portalRunId="20240120abc12345")

        event = {
            "detail": {
                "instrumentRunId": "run1",
                "sequenceRunId": "r.xxx",
                "linkedLibraries": ["L2400001", "L2400002"],
            }
        }
        handler(event, None)

        # Case should only be processed once despite two library matches
        mock_builder.assert_called_once()
        mock_emit.assert_called_once()
