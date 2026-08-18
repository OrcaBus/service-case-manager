import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from app.service.external_entity import get_or_create_external_entity
from app.service.case import link_case_to_external_entity_and_emit
from app.models import (
    Case,
    CaseExternalEntityLink,
    ExternalEntity,
    PendingExternalEntity,
)
from app.serializers.case import CaseExternalEntityLinkSerializer

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    Lambda handler that links a workflow run to a case via EventBridge WorkflowRunStateChange event.

    Matching a case to the workflow run is attempted in the following priority order:
    1. If the workflow run already exists as an ExternalEntity and is already linked to a
       case, there is nothing to do - skip.
    2. Otherwise, check whether the workflow run's portalRunId matches a PendingExternalEntity
       queued earlier when the case published a WorkflowRunUpdate DRAFT (see
       app.service.case._queue_pending_workflow_run_and_emit) - if found, that pending record
       is promoted to a real ExternalEntity (deleted once linked).
    3. Otherwise, fall back to matching via the workflow run's libraries against libraries
       already linked to a case.
    """
    logger.info(f"Processing event: {event}")

    detail = event.get("detail", {})

    workflow_run_orcabus_id = detail.get("orcabusId")
    portal_run_id = detail.get("portalRunId")
    libraries = detail.get("libraries", [])

    if not workflow_run_orcabus_id:
        logger.warning("Skipping event: no 'orcabusId' found in detail.")
        return

    # 1. If the workflow run already exists as an ExternalEntity and is already linked to a
    # case, there is nothing further to do.
    existing_entity = ExternalEntity.objects.filter(
        orcabus_id=workflow_run_orcabus_id
    ).first()
    if existing_entity:
        existing_link = (
            CaseExternalEntityLink.objects.filter(external_entity=existing_entity)
            .select_related("case")
            .first()
        )
        if existing_link:
            logger.info(
                f"Workflow run '{workflow_run_orcabus_id}' is already linked to case "
                f"'{existing_link.case.orcabus_id}', skipping."
            )
            return

    matched_cases: set[Case] = set()
    pending_entity = None

    # 2. Check for a case that queued this workflow run as a PendingExternalEntity
    # (keyed by portalRunId) when it published the WorkflowRunUpdate DRAFT. If found, this
    # takes priority over library-based matching below.
    if portal_run_id:
        pending_entity = (
            PendingExternalEntity.objects.filter(
                alias=portal_run_id, type="workflow_run", service_name="workflow"
            )
            .select_related("case")
            .first()
        )
        if pending_entity:
            matched_cases.add(pending_entity.case)
            logger.info(
                f"Found case '{pending_entity.case.orcabus_id}' via pending workflow run "
                f"portal_run_id '{portal_run_id}'."
            )

    # 3. No pending record found - fall back to matching cases via the workflow run's
    # linked libraries (deduplicated by case, since Case instances compare/hash by pk).
    if not pending_entity:
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
                    if case not in matched_cases:
                        matched_cases.add(case)
                        logger.info(
                            f"Found case '{case.orcabus_id}' via library '{lib_orcabus_id}'."
                        )
            except CaseExternalEntityLink.DoesNotExist:
                logger.debug(
                    f"No case linked to library '{lib_orcabus_id}', trying next."
                )
                continue

    if not matched_cases:
        logger.warning(
            f"No case found linked to any of the libraries or pending portal_run_id for "
            f"workflow run '{workflow_run_orcabus_id}'. Libraries checked: "
            f"{[lib.get('orcabusId') for lib in libraries]}, portal_run_id={portal_run_id}"
        )
        return

    # Get or create the workflow run as an external entity.
    # Http404 is intentionally not caught here: if the workflow run is not found in the
    # workflow service, we treat it as a hard failure so the Lambda retries the event.
    workflow_run_entity = get_or_create_external_entity(workflow_run_orcabus_id)

    for case in matched_cases:
        try:
            link = link_case_to_external_entity_and_emit(
                case, workflow_run_entity, history_user="system"
            )
            logger.info(
                f"Successfully linked workflow run '{workflow_run_orcabus_id}' to case '{case.orcabus_id}'."
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

    # Promotion complete — the pending queue record has served its purpose now that the
    # real ExternalEntity is created/linked above.
    if pending_entity:
        pending_entity.delete()
        logger.info(
            f"Deleted PendingExternalEntity for portal_run_id '{portal_run_id}' "
            f"(promoted to ExternalEntity '{workflow_run_orcabus_id}')"
        )
