import os
import logging

import requests

from app.models import CaseExternalEntityLink, ExternalEntity, State, User
from app.models.case import Case
from app.models.state import CaseStatus
from app.service.utils import get_service_jwt

logger = logging.getLogger(__name__)

# Terminal statuses — the case is closed and should never be auto-transitioned.
TERMINAL_STATUSES = frozenset(
    {
        CaseStatus.LOCKED,
        CaseStatus.COMPLETED,
        CaseStatus.ARCHIVED,
    }
)

SYSTEM_USER_EMAIL = "system@orcabus.org"


def _get_system_user() -> User:
    """Get or create the system user for automated state transitions."""
    user, _ = User.objects.get_or_create(email=SYSTEM_USER_EMAIL)
    return user


def _get_current_case_status(case: Case) -> str | None:
    """Return the latest non-archived status for a case, or None if no state exists."""
    latest_state = (
        State.objects.filter(case=case, is_archived=False)
        .order_by("-created_at")
        .first()
    )
    return latest_state.status if latest_state else None


def _has_open_sequencing_started(case: Case) -> bool:
    """
    Check whether the case has an open sequencing round — i.e. the most recent
    sequencing-related state (sequencing_started or sequencing_completed) is
    'sequencing_started' without a subsequent 'sequencing_completed'.

    Returns True if there is an unpaired sequencing_started (sequencing is in progress).
    Returns False if the last sequencing event is sequencing_completed or there are none.
    """
    latest_sequencing_state = (
        State.objects.filter(
            case=case,
            is_archived=False,
            status__in=[CaseStatus.SEQUENCING_STARTED, CaseStatus.SEQUENCING_COMPLETED],
        )
        .order_by("-created_at")
        .first()
    )

    if not latest_sequencing_state:
        return False

    return latest_sequencing_state.status == CaseStatus.SEQUENCING_STARTED


def _get_library_ids_for_case(case: Case) -> list[str]:
    """
    Retrieve all library aliases (e.g. 'L2400001') linked to a case
    via CaseExternalEntityLink where the external entity type is 'library'.
    """
    links = CaseExternalEntityLink.objects.filter(
        case=case,
        external_entity__type="library",
    ).select_related("external_entity")

    return [link.external_entity.alias for link in links if link.external_entity.alias]


def _all_sequence_runs_succeeded(library_ids: list[str]) -> bool:
    """
    Query the sequence run API for all sequence runs associated with the given
    library IDs. Returns True only if every returned sequence run has status
    'SUCCEEDED'. Returns False if there are no results or any run is not succeeded.
    """
    if not library_ids:
        return False

    jwt_token = get_service_jwt()
    headers = {"Authorization": f"Bearer {jwt_token}"}
    domain_name = os.environ.get("HOSTED_ZONE_NAME")
    url = f"https://sequence.{domain_name}/api/v1/sequence_run/"

    # Build query params with repeated libraryId keys
    params = {
        "rowsPerPage": 100,
        "libraryId": library_ids,
    }

    try:
        response = requests.get(url, headers=headers, params=params)
    except requests.RequestException as e:
        logger.error(f"Sequence service request failed: {e}")
        return False

    if response.status_code != 200:
        logger.warning(
            f"Sequence service returned {response.status_code} for libraries {library_ids}"
        )
        return False

    results = response.json().get("results", [])
    if not results:
        logger.info(f"No sequence runs found for libraries {library_ids}")
        return False

    for run in results:
        if run.get("status") != "SUCCEEDED":
            logger.info(
                f"Sequence run '{run.get('sequenceRunId')}' has status "
                f"'{run.get('status')}' — not all succeeded yet."
            )
            return False

    return True


def update_sequencing_state_for_sequence_run(sequence_run_orcabus_id: str) -> None:
    """
    Given a sequence run ID (alias), find all cases linked to it and transition
    them to 'sequencing_completed' if all related sequence runs have succeeded.

    This is the core logic invoked by the SequenceRunStateChange Lambda handler.

    Flow:
    1. Find the external entity matching the sequence run ID, then resolve all
       cases linked to that entity.
    2. For each linked case:
       a. Skip if the case is locked, completed, or archived.
          Skip if there is no open sequencing round (i.e. the most recent
          sequencing event is already "sequencing_completed" or no
          "sequencing_started" exists).
       b. Retrieve all library IDs associated with the case (via its external
          entities).
       c. Query the sequence run API to fetch all sequence runs for those
          libraries.
       d. If every related sequence run has succeeded, transition the case state
          to "sequencing_completed".
    """
    # Step 1: Find the external entity for this sequence run, then find linked cases.
    try:
        sequence_run_entity = ExternalEntity.objects.get(
            orcabus_id=sequence_run_orcabus_id, type="sequence_run"
        )
    except ExternalEntity.DoesNotExist:
        logger.warning(
            f"No external entity found for sequence run orcabus id of '{sequence_run_orcabus_id}'. "
            f"The sequence_run_linking handler may not have processed this run yet."
        )
        return

    case_links = CaseExternalEntityLink.objects.filter(
        external_entity=sequence_run_entity
    ).select_related("case")

    if not case_links.exists():
        logger.info(
            f"Sequence run '{sequence_run_orcabus_id}' is not linked to any case. Nothing to do."
        )
        return

    # Step 2: For each linked case, check if all sequencing is complete.
    for link in case_links:
        case = link.case
        current_status = _get_current_case_status(case)

        # 2a: Skip cases in terminal states.
        if current_status in TERMINAL_STATUSES:
            logger.info(
                f"Skipping case '{case.orcabus_id}': current status is '{current_status}'."
            )
            continue

        # 2a: Skip if there is no open sequencing round.
        if not _has_open_sequencing_started(case):
            logger.info(
                f"Skipping case '{case.orcabus_id}': no open sequencing round "
                f"(last sequencing event is already completed or none exists)."
            )
            continue

        # 2b: Get all library IDs for this case.
        library_ids = _get_library_ids_for_case(case)
        if not library_ids:
            logger.info(f"Case '{case.orcabus_id}' has no linked libraries. Skipping.")
            continue

        # 2c & 2d: Check if all sequence runs for these libraries have succeeded.
        if _all_sequence_runs_succeeded(library_ids):
            logger.info(
                f"All sequence runs succeeded for case '{case.orcabus_id}'. "
                f"Transitioning to '{CaseStatus.SEQUENCING_COMPLETED}'."
            )
            State.objects.create(
                case=case,
                status=CaseStatus.SEQUENCING_COMPLETED,
                created_by=_get_system_user(),
            )
        else:
            logger.info(
                f"Not all sequence runs have succeeded for case '{case.orcabus_id}'. "
                f"No state transition."
            )
