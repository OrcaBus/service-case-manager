import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist

from app.service.external_entity import get_or_create_external_entity
from app.service.case import link_case_to_external_entity_and_emit
from app.models import Case
from app.serializers.case import CaseExternalEntityLinkCreateSerializer

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda handler that links a metadata library entity to a case via EventBridge event."""
    logger.info(f"Processing event: {event}")

    detail = event.get("detail", {})
    data = detail.get("data", {})

    library_orcabus_id = data.get("orcabusId")
    request_form_id = data.get("requestFormId")

    if not library_orcabus_id or not request_form_id or request_form_id == "nan":
        logger.warning(
            f"Skipping event: no valid 'orcabusId' or 'requestFormId' in data: {data}"
        )
        return

    try:
        case = Case.objects.get(request_form_id=request_form_id)
    except ObjectDoesNotExist:
        logger.error(f"No case found for request_form_id: {request_form_id}")
        raise

    external_entity = get_or_create_external_entity(library_orcabus_id)

    try:

        link = link_case_to_external_entity_and_emit(
            case, external_entity, history_user="system"
        )
        logger.info(
            f"Successfully linked '{library_orcabus_id}' to case '{case.orcabus_id}'"
        )
        logger.info(f"Link data: {CaseExternalEntityLinkCreateSerializer(link).data}")

    except IntegrityError:
        logger.warning(
            f"Library '{library_orcabus_id}' is already linked to case '{case.orcabus_id}', skipping."
        )
