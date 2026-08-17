"""
Unit tests for draft_builder.build_cttso_workflow_run_draft.

Only the WorkflowRunUpdate draft event construction is tested here; the
other helper functions in draft_builder.py (generate_portal_run_id,
generate_workflow_run_name, construct_rgid, fetch_workflow_metadata) are
exercised indirectly through this function and are not tested in isolation.
"""

import os
from unittest.mock import patch, MagicMock, Mock
import requests

from app.service.draft_builder import build_cttso_workflow_run_draft


def _mock_workflow_metadata():
    return {
        "orcabusId": "wfl.test123",
        "name": "dragen-tso500-ctdna",
        "version": "4.3.6",
        "codeVersion": "1.0.0",
        "executionEngine": "unknown",
        "executionEnginePipelineId": "unknown",
        "validationState": "unknown",
    }


def test_build_cttso_workflow_run_draft_success():
    """
    Test that a WorkflowRunUpdate DRAFT event payload is properly created.

    Verifies that:
    - status is "DRAFT"
    - portalRunId and workflowRunName are generated
    - workflow metadata is included as-is
    - all valid library entities are included in the draft
    """
    with (
        patch.dict(
            os.environ,
            {
                "HOSTED_ZONE_NAME": "dev.umccr.org",
                "CTTSO_WORKFLOW_ORCABUS_ID": "wfl.cttso123",
            },
        ),
        patch("app.service.draft_builder.generate_portal_run_id") as mock_portal_id,
        patch("app.service.draft_builder.fetch_workflow_metadata") as mock_workflow,
    ):
        mock_portal_id.return_value = "20240120abc12345"
        mock_workflow.return_value = _mock_workflow_metadata()

        mock_case = Mock()
        mock_case.orcabus_id = "cas.test123"

        mock_lib1 = Mock()
        mock_lib1.orcabus_id = "lib.lib001"
        mock_lib1.alias = "L2400001"

        mock_lib2 = Mock()
        mock_lib2.orcabus_id = "lib.lib002"
        mock_lib2.alias = "L2400002"

        draft = build_cttso_workflow_run_draft(mock_case, [mock_lib1, mock_lib2])

        # Draft event structure
        assert draft["status"] == "DRAFT"
        assert draft["portalRunId"] == "20240120abc12345"
        assert (
            draft["workflowRunName"]
            == "umccr--automated--dragen-tso500-ctdna--4-3-6--20240120abc12345"
        )

        # Workflow metadata passed through as-is
        assert draft["workflow"]["orcabusId"] == "wfl.test123"
        assert draft["workflow"]["name"] == "dragen-tso500-ctdna"
        assert draft["workflow"]["version"] == "4.3.6"

        # Libraries included
        assert len(draft["libraries"]) == 2
        assert draft["libraries"][0]["orcabusId"] == "lib.lib001"
        assert draft["libraries"][0]["libraryId"] == "L2400001"
        assert draft["libraries"][1]["orcabusId"] == "lib.lib002"
        assert draft["libraries"][1]["libraryId"] == "L2400002"

        # Verify collaborators were called correctly
        mock_portal_id.assert_called_once()
        mock_workflow.assert_called_once_with(workflow_orcabus_id="wfl.cttso123")


def test_build_cttso_workflow_run_draft_missing_cttso_workflow_orcabus_id():
    """Test RuntimeError is raised when CTTSO_WORKFLOW_ORCABUS_ID is not set."""
    with (
        patch.dict(os.environ, {"HOSTED_ZONE_NAME": "dev.umccr.org"}, clear=True),
        patch("app.service.draft_builder.generate_portal_run_id") as mock_portal_id,
    ):
        mock_portal_id.return_value = "20240120abc12345"

        mock_case = Mock()
        mock_case.orcabus_id = "cas.test123"

        mock_lib = Mock()
        mock_lib.orcabus_id = "lib.lib001"
        mock_lib.alias = "L2400001"

        try:
            build_cttso_workflow_run_draft(mock_case, [mock_lib])
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "CTTSO_WORKFLOW_ORCABUS_ID" in str(e)


def test_build_cttso_workflow_run_draft_skips_invalid_libraries():
    """Test that library entities missing orcabus_id/alias are skipped from the draft."""
    with (
        patch.dict(
            os.environ,
            {
                "HOSTED_ZONE_NAME": "dev.umccr.org",
                "CTTSO_WORKFLOW_ORCABUS_ID": "wfl.cttso123",
            },
        ),
        patch("app.service.draft_builder.generate_portal_run_id") as mock_portal_id,
        patch("app.service.draft_builder.fetch_workflow_metadata") as mock_workflow,
    ):
        mock_portal_id.return_value = "20240120abc12345"
        mock_workflow.return_value = _mock_workflow_metadata()

        mock_case = Mock()
        mock_case.orcabus_id = "cas.test123"

        mock_lib_valid = Mock()
        mock_lib_valid.orcabus_id = "lib.lib001"
        mock_lib_valid.alias = "L2400001"

        mock_lib_invalid = Mock()
        mock_lib_invalid.orcabus_id = None  # Missing!
        mock_lib_invalid.alias = "L2400002"

        draft = build_cttso_workflow_run_draft(
            mock_case, [mock_lib_valid, mock_lib_invalid]
        )

        # Only the valid library should be present in the created event
        assert len(draft["libraries"]) == 1
        assert draft["libraries"][0]["orcabusId"] == "lib.lib001"


def test_build_cttso_workflow_run_draft_all_libraries_fail():
    """Test that ValueError is raised when no libraries have valid orcabus_id/alias."""
    with (
        patch.dict(
            os.environ,
            {
                "HOSTED_ZONE_NAME": "dev.umccr.org",
                "CTTSO_WORKFLOW_ORCABUS_ID": "wfl.cttso123",
            },
        ),
        patch("app.service.draft_builder.generate_portal_run_id") as mock_portal_id,
        patch("app.service.draft_builder.fetch_workflow_metadata") as mock_workflow,
    ):
        mock_portal_id.return_value = "20240120abc12345"
        mock_workflow.return_value = _mock_workflow_metadata()

        mock_case = Mock()
        mock_case.orcabus_id = "cas.test123"

        mock_lib1 = Mock()
        mock_lib1.orcabus_id = None
        mock_lib1.alias = "L2400001"

        mock_lib2 = Mock()
        mock_lib2.orcabus_id = "lib.lib002"
        mock_lib2.alias = None

        try:
            build_cttso_workflow_run_draft(mock_case, [mock_lib1, mock_lib2])
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No libraries could be successfully processed" in str(e)
            assert "cas.test123" in str(e)


def test_build_cttso_workflow_run_draft_workflow_metadata_failure():
    """Test that workflow metadata fetch failure propagates (draft event not created)."""
    with (
        patch.dict(
            os.environ,
            {
                "HOSTED_ZONE_NAME": "dev.umccr.org",
                "CTTSO_WORKFLOW_ORCABUS_ID": "wfl.cttso123",
            },
        ),
        patch("app.service.draft_builder.generate_portal_run_id") as mock_portal_id,
        patch("app.service.draft_builder.fetch_workflow_metadata") as mock_workflow,
    ):
        mock_portal_id.return_value = "20240120abc12345"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_workflow.side_effect = requests.HTTPError(response=mock_response)

        mock_case = Mock()
        mock_case.orcabus_id = "cas.test123"

        mock_lib = Mock()
        mock_lib.orcabus_id = "lib.lib001"
        mock_lib.alias = "L2400001"

        try:
            build_cttso_workflow_run_draft(mock_case, [mock_lib])
            assert False, "Should have raised HTTPError"
        except requests.HTTPError:
            pass  # Expected behavior - error propagates to caller
