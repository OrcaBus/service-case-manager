"""
Helper functions for constructing workflow run draft event payloads.

This module provides utility functions for generating unique identifiers and names
for workflow run drafts in the OrcaBus platform.
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict

import requests

from app.service.http_client import http_get_json

logger = logging.getLogger(__name__)


CTTSO_ORCABUS_ID = os.environ.get(
    "CTTSO_WORKFLOW_ORCABUS_ID", "01JBG0KCS252ZNW4384CR4H8YN"
)


def generate_portal_run_id() -> str:
    """
    Generate a unique portal run ID in format YYYYMMDD{uuid8}.

    The portal run ID consists of:
    - Current UTC date in YYYYMMDD format (8 characters)
    - First 8 characters of a randomly generated UUID

    Returns:
        Unique portal run ID string (16 characters total)

    Example:
        "20240120abc12345"
    """
    # Get current UTC datetime
    now = datetime.now(timezone.utc)

    # Format date as YYYYMMDD
    date_prefix = now.strftime("%Y%m%d")

    # Generate UUID and take the first 8 characters
    uuid_suffix = str(uuid.uuid4())[:8]

    # Concatenate date and UUID
    portal_run_id = date_prefix + uuid_suffix

    return portal_run_id


def generate_workflow_run_name(
    workflow_name: str, workflow_version: str, portal_run_id: str
) -> str:
    """
    Generate workflow run name in standard format.

    The workflow run name follows the convention:
    umccr--automated--{workflow_name}--{workflow_version}--{portal_run_id}

    Args:
        workflow_name: Name of the workflow (e.g., "dragen-tso500-ctdna")
        workflow_version: Version string (e.g., "4.3.6")
        portal_run_id: Unique portal run identifier

    Returns:
        Formatted workflow run name (lowercase)

    Example:
        generate_workflow_run_name("dragen-tso500-ctdna", "4.3.6", "20240120abc12345")
        -> "umccr--automated--dragen-tso500-ctdna--4-3-6--20240120abc12345"
    """
    # Replace dots in version with dashes
    version_formatted = workflow_version.replace(".", "-")

    # Construct name using double-dash separator
    workflow_run_name = (
        f"umccr--automated--{workflow_name}--{version_formatted}--{portal_run_id}"
    )

    # Ensure lowercase
    return workflow_run_name.lower()


def construct_rgid(lane: str, index: str, instrument_run_id: str) -> str:
    """
    Construct readset group ID from lane, index, and instrument run ID.

    The RGID format is: {lane}.{index}.{instrument_run_id}

    Args:
        lane: Lane number or identifier (e.g., "1", "2")
        index: Index sequence (e.g., "ACGTACGT")
        instrument_run_id: Instrument run identifier (e.g., "240101_A00001_0001_ABCDEFGHI")

    Returns:
        Formatted readset group ID

    Example:
        construct_rgid("1", "ACGTACGT", "240101_A00001_0001_ABCDEFGHI")
        -> "1.ACGTACGT.240101_A00001_0001_ABCDEFGHI"
    """
    return f"{lane}.{index}.{instrument_run_id}"


def fetch_readsets_for_library(library_orcabus_id: str) -> List[Dict[str, str]]:
    """
    Query FASTQ Service for readset details for a specific library.

    Constructs a URL dynamically using HOSTED_ZONE_NAME environment variable,
    queries the FASTQ Service API, and extracts readset records with constructed RGIDs.

    This function tolerates failures and returns an empty list on errors to support
    partial processing of multiple libraries.

    Args:
        library_orcabus_id: OrcaBus ID of the library (e.g., "lib.xyz789")

    Returns:
        List of readset dictionaries, each containing:
        - orcabusId: Readset OrcaBus ID
        - rgid: Constructed readset group ID in format "{lane}.{index}.{instrumentRunId}"
        Returns empty list if request fails or response is malformed.

    Example:
        [
            {
                "orcabusId": "rds.def456",
                "rgid": "1.ACGTACGT.240101_A00001_0001_ABCDEFGHI"
            }
        ]

    Raises:
        RuntimeError: HOSTED_ZONE_NAME environment variable not set (when constructing URL)
    """
    # Construct URL at call time using environment variable
    hosted_zone_name = os.environ.get("HOSTED_ZONE_NAME")
    if not hosted_zone_name:
        raise RuntimeError("HOSTED_ZONE_NAME environment variable not set")

    fastq_url = f"https://fastq.{hosted_zone_name}/api/v1/readset/"

    try:
        # Make authenticated HTTP GET request with query parameter
        response_data = http_get_json(
            fastq_url, params={"library_orcabus_id": library_orcabus_id}
        )

        # Extract readset records from response
        readsets = []
        results = response_data.get("results", [])

        for readset_data in results:
            try:
                # Extract required fields
                orcabus_id = readset_data["orcabusId"]
                lane = readset_data["lane"]
                index = readset_data["index"]
                instrument_run_id = readset_data["instrumentRunId"]

                # Construct rgid using helper function
                rgid = construct_rgid(lane, index, instrument_run_id)

                # Add to readsets list
                readsets.append({"orcabusId": orcabus_id, "rgid": rgid})

            except KeyError as e:
                # Malformed readset record - log error and skip this readset
                logger.error(
                    f"Malformed readset record for library {library_orcabus_id}: missing field {e}"
                )
                continue

        return readsets

    except requests.HTTPError as e:
        # Non-200 response - log warning and return empty list
        status_code = e.response.status_code if e.response else "unknown"
        logger.warning(
            f"FASTQ service returned {status_code} for library {library_orcabus_id}"
        )
        return []

    except (KeyError, TypeError, ValueError) as e:
        # Malformed response body - log error and return empty list
        logger.error(
            f"Failed to extract readsets from FASTQ service response for library {library_orcabus_id}: {e}"
        )
        return []

    except Exception as e:
        # Unexpected error - log error and return empty list
        logger.error(
            f"Unexpected error fetching readsets for library {library_orcabus_id}: {e}"
        )
        return []


def fetch_workflow_metadata(workflow_orcabus_id: str) -> Dict[str, str]:
    """
    Query Workflow Service for workflow metadata by OrcaBus ID.

    Constructs the Workflow Service URL dynamically from HOSTED_ZONE_NAME
    environment variable and queries the detail endpoint for the specified
    workflow, pinning the exact name+version combination.

    Args:
        workflow_orcabus_id: Exact OrcaBus ID of the workflow to query
            (e.g., "01ARZ3NDEKTSV4RRFFQ69G5FAV").

    Returns:
        The parsed JSON response as-is, e.g.:
        {
          "orcabusId": "wfl.01ARZ3NDEKTSV4RRFFQ69G5FAV",
          "name": "tso500-ctdna",
          "version": "1.0.0",
          "codeVersion": "0.0.0",
          "executionEngine": "Unknown",
          "executionEnginePipelineId": "Unknown",
          "validationState": "UNVALIDATED"
        }

    Raises:
        ValueError: workflow_orcabus_id not supplied
        RuntimeError: HOSTED_ZONE_NAME environment variable not set
        requests.HTTPError: Non-200 status code from Workflow Service
    """
    if not workflow_orcabus_id:
        raise ValueError(
            "workflow_orcabus_id must be provided to fetch workflow metadata."
        )

    # Get HOSTED_ZONE_NAME from environment (fail fast if not set)
    hosted_zone_name = os.environ.get("HOSTED_ZONE_NAME")
    if not hosted_zone_name:
        raise RuntimeError(
            "HOSTED_ZONE_NAME environment variable not set. "
            "Cannot construct Workflow Service URL."
        )

    # Construct Workflow Service detail URL at call time
    workflow_url = (
        f"https://workflow.{hosted_zone_name}/api/v1/workflow/{workflow_orcabus_id}/"
    )

    logger.info(f"Fetching workflow metadata for orcabusId '{workflow_orcabus_id}'")
    workflow_data = http_get_json(workflow_url)

    logger.info(
        f"Successfully fetched workflow metadata: {workflow_data.get('orcabusId')}"
    )
    return workflow_data


def build_cttso_workflow_run_draft(case, library_entities: List) -> dict:
    """
    Build a complete workflow run draft event payload for the cttso (ctTSO500)
    workflow.

    NOTE: This function is currently specific to the cttso workflow — it always
    fetches metadata for the workflow identified by the CTTSO_WORKFLOW_ORCABUS_ID
    environment variable. If/when other case/workflow types need draft workflow
    runs built, consider generalizing this by accepting a `workflow_orcabus_id`
    (or similar workflow-type parameter) instead of reading a hardcoded env var,
    rather than adding more cttso-specific functions.

    This function orchestrates all helper functions to:
    1. Generate a unique portal run ID
    2. Fetch workflow metadata from the Workflow Service (pinned to the cttso
       workflow via CTTSO_WORKFLOW_ORCABUS_ID)
    3. Generate a workflow run name
    4. Construct LibraryDetail objects with appropriate library entities
    5. Build and return a WorkflowRunUpdate Pydantic model

    Args:
        case: Django Case model instance
        library_entities: List of ExternalEntity records with type="library"

    Returns:
        WorkflowRunUpdate Pydantic model instance representing the draft workflow run

    Raises:
        ValueError: If no libraries could be successfully processed (all missing
                   required fields, or empty list)
        requests.HTTPError: If workflow metadata fetch fails
        RuntimeError: If HOSTED_ZONE_NAME or CTTSO_WORKFLOW_ORCABUS_ID environment
                     variable is not set

    Example:
        draft = build_cttso_workflow_run_draft(case, library_entities)
        # Returns WorkflowRunUpdate model with status="DRAFT"
    """
    # Generate unique portal run ID
    portal_run_id = generate_portal_run_id()
    logger.info(f"Generated portal run ID: {portal_run_id}")

    workflow_orcabus_id_to_fetch = os.environ.get("CTTSO_WORKFLOW_ORCABUS_ID")
    if not workflow_orcabus_id_to_fetch:
        raise RuntimeError(
            "CTTSO_WORKFLOW_ORCABUS_ID environment variable not set. "
            "Cannot fetch workflow metadata."
        )

    workflow_metadata = fetch_workflow_metadata(
        workflow_orcabus_id=workflow_orcabus_id_to_fetch
    )

    # Generate workflow run name
    workflow_run_name = generate_workflow_run_name(
        workflow_metadata["name"], workflow_metadata["version"], portal_run_id
    )
    logger.info(f"Generated workflow run name: {workflow_run_name}")

    # Build library detail objects (using camelCase field names), skipping
    # any entity missing the required fields.
    successful_libraries = []
    for library_entity in library_entities:
        if not library_entity.orcabus_id or not library_entity.alias:
            logger.warning(
                f"Skipping library entity with missing orcabus_id/alias: {library_entity}"
            )
            continue

        successful_libraries.append(
            {
                "orcabusId": library_entity.orcabus_id,
                "libraryId": library_entity.alias,
            }
        )

    # Verify at least one library was successfully processed
    if not successful_libraries:
        error_msg = (
            f"No libraries could be successfully processed for case {case.orcabus_id}. "
            "Cannot create workflow run draft without valid libraries."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # workflow_metadata is already returned as-is from the Workflow Service
    # with camelCase field names matching the Pydantic model.
    workflow = workflow_metadata

    # Construct WorkflowRunUpdate payload (using camelCase field names)
    workflow_run_draft = {
        "status": "DRAFT",
        "portalRunId": portal_run_id,
        "workflowRunName": workflow_run_name,
        "workflow": workflow,
        "libraries": successful_libraries,
    }

    logger.info(
        f"Successfully built workflow run draft for case {case.orcabus_id}: "
        f"{len(successful_libraries)} libraries, portal_run_id={portal_run_id}"
    )

    return workflow_run_draft
