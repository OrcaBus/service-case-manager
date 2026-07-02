import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from app.service.external_entity import get_or_create_external_entity
from app.service.case import link_case_to_external_entity_and_emit
from app.models import CaseExternalEntityLink
from app.serializers.case import CaseExternalEntityLinkSerializer

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    Lambda handler that links a workflow run to a case via EventBridge WorkflowRunStateChange event.

    The handler inspects the libraries attached to the workflow run and looks for a case
    that already has one of those libraries linked as an external entity. If found, the
    workflow run itself is also linked to that case as an external entity.
    """
    logger.info(f"Processing event: {event}")

    detail = event.get("detail", {})

    workflow_run_orcabus_id = detail.get("orcabusId")
    libraries = detail.get("libraries", [])

    if not workflow_run_orcabus_id:
        logger.warning("Skipping event: no 'orcabusId' found in detail.")
        return

    if not libraries:
        logger.warning(
            f"Skipping event: no libraries found in detail for workflow run '{workflow_run_orcabus_id}'."
        )
        return

    # Find all cases linked to any of the libraries (deduplicated by case id)
    case_to_library_map = {}  # case_orcabus_id -> (case, matched_library_id)
    for lib in libraries:
        lib_orcabus_id = lib.get("orcabusId")
        if not lib_orcabus_id:
            continue

        try:
            links = CaseExternalEntityLink.objects.select_related("case").filter(
                external_entity__orcabus_id=lib_orcabus_id
            )
            for link in links:
                case = link.case
                if case.orcabus_id not in case_to_library_map:
                    case_to_library_map[case.orcabus_id] = (case, lib_orcabus_id)
                    logger.info(
                        f"Found case '{case.orcabus_id}' via library '{lib_orcabus_id}'."
                    )
        except CaseExternalEntityLink.DoesNotExist:
            logger.debug(f"No case linked to library '{lib_orcabus_id}', trying next.")
            continue

    if not case_to_library_map:
        logger.warning(
            f"No case found linked to any of the libraries for workflow run "
            f"'{workflow_run_orcabus_id}'. Libraries checked: "
            f"{[lib.get('orcabusId') for lib in libraries]}"
        )
        return

    # Get or create the workflow run as an external entity.
    # Http404 is intentionally not caught here: if the workflow run is not found in the
    # workflow service, we treat it as a hard failure so the Lambda retries the event.
    workflow_run_entity = get_or_create_external_entity(workflow_run_orcabus_id)

    for case_orcabus_id, (case, matched_library_id) in case_to_library_map.items():
        try:
            link = link_case_to_external_entity_and_emit(
                case, workflow_run_entity, history_user="system"
            )
            logger.info(
                f"Successfully linked workflow run '{workflow_run_orcabus_id}' to case '{case.orcabus_id}' "
                f"(matched via library '{matched_library_id}')."
            )
            logger.info(f"Link data: {CaseExternalEntityLinkSerializer(link).data}")

        except ValidationError as e:
            # Case is locked / completed / archived — blocked at the model level.
            # Log a warning and continue to the next case; no retry needed.
            logger.warning(
                f"Skipping workflow run link for '{workflow_run_orcabus_id}' to case '{case.orcabus_id}': {e.detail}"
            )

        except IntegrityError:
            logger.warning(
                f"Workflow run '{workflow_run_orcabus_id}' is already linked to case '{case.orcabus_id}', skipping."
            )
