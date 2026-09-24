import os
import logging

import requests

from app.models import CaseExternalEntityLink, ExternalEntity, State, User
from app.models.case import Case
from app.models.state import CaseStatus, TERMINAL_STATUSES
from app.service.utils import get_service_jwt

logger = logging.getLogger(__name__)

SYSTEM_USER_EMAIL = "system@orcabus.org"


def _get_system_user() -> User:
    """Get or create the system user for automated state transitions."""
    user, _ = User.objects.get_or_create(email=SYSTEM_USER_EMAIL)
    return user


def _get_current_case_status(case: Case) -> str | None:
    """Return the latest non-archived status for a case, or None if no state exists."""
    latest_state = (
        State.objects.filter(case=case, is_archived=False)
        .order_by("-event_date")
        .first()
    )
    return latest_state.status if latest_state else None


def _get_workflow_run_entities_for_case(case: Case) -> list[ExternalEntity]:
    """
    Retrieve all workflow_run external entities linked to a case
    via CaseExternalEntityLink where the external entity type is 'workflow_run'.
    """
    links = CaseExternalEntityLink.objects.filter(
        case=case,
        external_entity__type="workflow_run",
    ).select_related("external_entity")

    return [link.external_entity for link in links]


def _any_workflow_run_ongoing(workflow_run_entities: list[ExternalEntity]) -> bool:
    """
    Return True if at least one of the given workflow run entities is still ongoing.

    Queries the workflow run API once for all runs using a multi-value orcabusId
    filter combined with is_ongoing:
        https://workflow.{domain}/api/v1/workflowrun/?is_ongoing=true&orcabusId=<id1>&orcabusId=<id2>...

    Any run that appears in the is_ongoing=true result set is still running. If the
    result set is non-empty, at least one run is ongoing.

    Raises requests.RequestException if the workflow API call fails, so the caller
    can treat it as a hard failure and retry rather than mis-classifying state.
    """
    if not workflow_run_entities:
        return False

    jwt_token = get_service_jwt()
    headers = {"Authorization": f"Bearer {jwt_token}"}
    domain_name = os.environ.get("HOSTED_ZONE_NAME")
    url = f"https://workflow.{domain_name}/api/v1/workflowrun/"

    params = {
        "isOngoing": "true",
        "orcabusId": [entity.orcabus_id for entity in workflow_run_entities],
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    results = response.json().get("results", [])
    if results:
        ongoing_ids = [result.get("orcabusId") for result in results]
        logger.info(f"Workflow runs still ongoing: {ongoing_ids}")
    return len(results) > 0


def update_bioinfo_state_for_workflow_run(workflow_run_orcabus_id: str) -> None:
    """
    Given a workflow run orcabus id, find all cases linked to it and transition
    them between 'bioinformatics_started' and 'bioinformatics_completed' based on
    whether any of the case's linked workflow runs are still ongoing.

    This is the core logic invoked by the WorkflowRunStateChange Lambda handler.

    Flow:
    1. Find the external entity matching the workflow run orcabus id, then resolve
       all cases linked to that entity.
    2. For each linked case:
       a. Skip if the case is locked, completed, or archived (terminal status).
       b. Gather all workflow_run external entities linked to the case.
       c. Query the workflow API once for all runs (multi-value orcabusId filter):
          - If ANY run is still ongoing  -> target status 'bioinformatics_started'.
          - If NONE is ongoing (all done) -> target status 'bioinformatics_completed'.
       d. Skip if the case's current status already equals the target status
          (avoid duplicate consecutive states); otherwise create the new State.
    """
    # Step 1: Find the external entity for this workflow run, then find linked cases.
    try:
        workflow_run_entity = ExternalEntity.objects.get(
            orcabus_id=workflow_run_orcabus_id, type="workflow_run"
        )
    except ExternalEntity.DoesNotExist:
        logger.warning(
            f"No external entity found for workflow run orcabus id of '{workflow_run_orcabus_id}'. "
            f"The workflow_run_linking handler may not have processed this run yet."
        )
        return

    case_links = CaseExternalEntityLink.objects.filter(
        external_entity=workflow_run_entity
    ).select_related("case")

    if not case_links.exists():
        logger.info(
            f"Workflow run '{workflow_run_orcabus_id}' is not linked to any case. Nothing to do."
        )
        return

    # Step 2: For each linked case, recompute the bioinformatics state.
    for link in case_links:
        case = link.case
        current_status = _get_current_case_status(case)

        # 2a: Skip cases in terminal states.
        if current_status in TERMINAL_STATUSES:
            logger.info(
                f"Skipping case '{case.orcabus_id}': current status is '{current_status}'."
            )
            continue

        # 2b: Gather all workflow run entities for this case.
        workflow_run_entities = _get_workflow_run_entities_for_case(case)
        if not workflow_run_entities:
            logger.info(
                f"Case '{case.orcabus_id}' has no linked workflow runs. Skipping."
            )
            continue

        # 2c: Determine the target status from the ongoing check.
        target_status = (
            CaseStatus.BIOINFORMATICS_STARTED
            if _any_workflow_run_ongoing(workflow_run_entities)
            else CaseStatus.BIOINFORMATICS_COMPLETED
        )

        # 2d: Skip if the case is already in the target status.
        if current_status == target_status:
            logger.info(
                f"Case '{case.orcabus_id}' is already '{current_status}'. No state transition."
            )
            continue

        logger.info(
            f"Transitioning case '{case.orcabus_id}' from '{current_status}' to '{target_status}'."
        )
        State.objects.create(
            case=case,
            status=target_status,
            created_by=_get_system_user(),
        )
