import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from app.service.external_entity import get_or_create_sequence_run_entity
from app.service.case import link_case_to_external_entity_and_emit
from app.models import CaseExternalEntityLink, State, User
from app.models.state import CaseStatus
from app.serializers.case import CaseExternalEntityLinkSerializer

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Statuses that should not be auto-transitioned.
TERMINAL_STATUSES = frozenset(
    {CaseStatus.LOCKED, CaseStatus.COMPLETED, CaseStatus.ARCHIVED}
)

SYSTEM_USER_EMAIL = "system@orcabus.org"


def _get_system_user() -> User:
    """Get or create the system user for automated state transitions."""
    user, _ = User.objects.get_or_create(email=SYSTEM_USER_EMAIL)
    return user


def _transition_to_sequencing_started(case, sequence_run_id: str) -> None:
    """
    Transition the case to 'sequencing_started' after a sequence run is linked.

    Skips the transition when:
    - The case is in a terminal status (locked, completed, archived).
    - The case already has an open 'sequencing_started' state (i.e. the most
      recent sequencing-related state is already sequencing_started).

    Allows the transition when:
    - The case has no sequencing-related states yet.
    - The most recent sequencing-related state is 'sequencing_completed'
      (additional sequencing round — go back to started).
    """
    latest_state = (
        State.objects.filter(case=case, is_archived=False)
        .order_by("-created_at")
        .first()
    )
    current_status = latest_state.status if latest_state else None

    if current_status in TERMINAL_STATUSES:
        logger.info(
            f"Skipping sequencing_started transition for case '{case.orcabus_id}': "
            f"current status is '{current_status}'."
        )
        return

    # Check if sequencing is already in progress (open sequencing_started without
    # a subsequent sequencing_completed). If the latest sequencing event is
    # sequencing_completed, we allow the transition back to started for a new round.
    latest_sequencing_state = (
        State.objects.filter(
            case=case,
            is_archived=False,
            status__in=[CaseStatus.SEQUENCING_STARTED, CaseStatus.SEQUENCING_COMPLETED],
        )
        .order_by("-created_at")
        .first()
    )
    if (
        latest_sequencing_state
        and latest_sequencing_state.status == CaseStatus.SEQUENCING_STARTED
    ):
        logger.info(
            f"Case '{case.orcabus_id}' already has an open 'sequencing_started' state. "
            f"Skipping duplicate transition for sequence run '{sequence_run_id}'."
        )
        return

    # Create the sequencing_started state.
    State.objects.create(
        case=case,
        status=CaseStatus.SEQUENCING_STARTED,
        created_by=_get_system_user(),
    )
    logger.info(
        f"Transitioned case '{case.orcabus_id}' to '{CaseStatus.SEQUENCING_STARTED}' "
        f"after linking sequence run '{sequence_run_id}'."
    )


def handler(event, context):
    """
    Lambda handler that links a sequence run to a case via an EventBridge
    SequenceRunStateChange event.

    The handler inspects the libraries attached to the sequence run and looks for a case
    that already has one of those libraries linked as an external entity. If found, the
    sequence run itself is also linked to that case as an external entity.

    After a successful link, the case is automatically transitioned to
    'sequencing_started' (unless it is already in that state or in a terminal state).

    Expected event detail shape:
        {
            "instrumentRunId": "...",
            "sequenceRunId": "r.xxx",
            "timeStamp": "...",
            "linkedLibraries": ["L0000001", "L0000002", ...]
        }
    """
    logger.info(f"Processing event: {event}")

    detail = event.get("detail", {})

    sequence_run_id = detail.get("sequenceRunId")
    linked_libraries = detail.get("linkedLibraries", [])

    if not sequence_run_id:
        logger.warning("Skipping event: no 'sequenceRunId' found in detail.")
        return

    if not linked_libraries:
        logger.warning(
            f"Skipping event: no libraries found in detail for sequence run '{sequence_run_id}'."
        )
        return

    # Find all cases linked to any of the libraries (deduplicated by case id).
    # linkedLibraries contains plain library IDs (e.g. "L2600353") which are
    # stored as the 'alias' on library ExternalEntity records.
    case_to_library_map = {}  # case_orcabus_id -> (case, matched_library_id)
    for library_id in linked_libraries:
        try:
            links = CaseExternalEntityLink.objects.select_related("case").filter(
                external_entity__alias=library_id,
                external_entity__type="library",
            )
            for link in links:
                case = link.case
                if case.orcabus_id not in case_to_library_map:
                    case_to_library_map[case.orcabus_id] = (case, library_id)
                    logger.info(
                        f"Found case '{case.orcabus_id}' via library '{library_id}'."
                    )
        except CaseExternalEntityLink.DoesNotExist:
            logger.debug(f"No case linked to library '{library_id}', trying next.")
            continue

    if not case_to_library_map:
        logger.warning(
            f"No case found linked to any of the libraries for sequence run "
            f"'{sequence_run_id}'. Libraries checked: {linked_libraries}"
        )
        return

    # Get or create the sequence run as an external entity.
    # The sequenceRunId is NOT the orcabus_id — get_or_create_sequence_run_entity
    # first queries the sequence service to resolve the real orcabusId.
    # Http404 is intentionally not caught here: if the sequence run is not found in the
    # sequence service, we treat it as a hard failure so the Lambda retries the event.
    sequence_run_entity = get_or_create_sequence_run_entity(sequence_run_id)

    for case_orcabus_id, (case, matched_library_id) in case_to_library_map.items():
        try:
            link = link_case_to_external_entity_and_emit(
                case, sequence_run_entity, history_user="system"
            )
            logger.info(
                f"Successfully linked sequence run '{sequence_run_id}' to case '{case.orcabus_id}' "
                f"(matched via library '{matched_library_id}')."
            )
            logger.info(f"Link data: {CaseExternalEntityLinkSerializer(link).data}")

            # Transition the case to 'sequencing_started' after successful linking.
            _transition_to_sequencing_started(case, sequence_run_id)

        except ValidationError as e:
            # Case is locked / completed / archived — blocked at the model level.
            # Log a warning and continue to the next case; no retry needed.
            logger.warning(
                f"Skipping sequence run link for '{sequence_run_id}' to case '{case.orcabus_id}': {e.detail}"
            )

        except IntegrityError:
            logger.warning(
                f"Sequence run '{sequence_run_id}' is already linked to case '{case.orcabus_id}', skipping."
            )
