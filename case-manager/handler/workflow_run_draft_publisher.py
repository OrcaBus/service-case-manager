"""
AWS Lambda handler for workflow run draft publisher.

This handler is triggered by EventBridge events carrying the libraries linked to a
sequencing run (the same event shape consumed by the sequence run linking handler).
For each case found to be linked to one of those libraries, and whose type is
'cttso', it delegates to app.service.case.publish_cttso_workflow_run_draft_for_case
to build and emit a draft workflow run event to EventBridge for downstream
processing by the Workflow Manager service.

MVP scope: only "cttso" cases are supported today (see app/service/case.py). Other
case types are intentionally skipped for now. Extending to additional case
types/workflows will require making the case-type -> workflow mapping
configurable rather than a single hardcoded check + workflow name.

Entry Point:
    handler(event, context) - AWS Lambda handler function

Workflow:
    1. Initialize Django ORM
    2. Extract linked libraries from the EventBridge event
    3. Find the case(s) linked to any of those libraries
    4. Delegate each case to the case service, which validates case type,
       checks for workflow run deduplication, builds the draft payload, and
       emits the WorkflowRunUpdate event to EventBridge
"""

import logging
import os

import django

# Initialize Django before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

# Import Django-dependent modules after setup
from app.service.case import publish_cttso_workflow_run_draft_for_case
from app.service.external_entity import find_cases_linked_to_libraries

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    AWS Lambda handler for workflow run draft publisher.

    This handler processes EventBridge events carrying the libraries linked to a
    sequencing run and creates related workflow run DRAFTs. It looks
    up the case(s) linked to any of those libraries, then delegates all
    validation, deduplication, and publishing logic to the case service.

    Args:
        event: EventBridge event containing the libraries linked to a sequencing run
        context: AWS Lambda context object

    Returns:
        None (logs success/failure, raises exceptions for retries)

    Raises:
        Exception: Service call failures (triggers Lambda retry)

    Event Structure:
        {
            "instrumentRunId": "...",
            "sequenceRunId": "r.xxx",
            "timeStamp": "...",
            "linkedLibraries": ["L0000001", "L0000002", ...]
        }

    Processing Logic:
        - Skip events with no 'linkedLibraries' in detail (log warning, return early)
        - Find case(s) linked to any of the libraries via CaseExternalEntityLink
          (library aliases match "linkedLibraries" entries)
        - Skip if no case is found linked to any library (log warning, return early)
        - For each matching case, delegate to
          publish_cttso_workflow_run_draft_for_case, which will dispatch the
          event accordingly.
    """
    logger.info(f"Processing event: {event}")

    detail = event.get("detail", {})
    linked_libraries = detail.get("linkedLibraries", [])

    if not linked_libraries:
        logger.warning("Skipping event: no 'linkedLibraries' found in detail.")
        return

    case_map = find_cases_linked_to_libraries(linked_libraries)

    if not case_map:
        logger.warning(
            f"No case found linked to any of the libraries: {linked_libraries}"
        )
        return

    for case in case_map.values():
        publish_cttso_workflow_run_draft_for_case(case)
