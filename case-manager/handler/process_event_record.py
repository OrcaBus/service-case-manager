import django
import os
import logging
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from django.shortcuts import get_object_or_404
from app.models import Case, ExternalEntity, CaseExternalEntityLink
from app.schemas.events.case_relationship_update_model import (
    CaseRelationshipUpdate,
    Action,
)
from app.serializers.case import CaseExternalEntityLinkCreateSerializer
from app.service.case import (
    link_case_to_external_entity_and_emit,
    unlink_case_to_external_entity_and_emit,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info(f"Processing event: {json.dumps(event)}")
    event_details = event.get("detail", None)

    try:
        case_update_event = CaseRelationshipUpdate(**event_details)
        case = get_object_or_404(Case, pk=case_update_event.case["orcabus_id"])
        external_entity_json = case_update_event.externalEntity

        if case_update_event.action == Action.CREATE:
            external_entity, _is_created = ExternalEntity.objects.get_or_create(
                orcabus_id=external_entity_json["orcabus_id"],
                defaults=external_entity_json,
            )

            linked = link_case_to_external_entity_and_emit(
                case=case,
                external_entity=external_entity,
                added_via=case_update_event.addedVia,
            )
            logger.info(
                f"Successfully linked case {case.orcabus_id} to external entity {external_entity.orcabus_id}"
            )
            logger.info(CaseExternalEntityLinkCreateSerializer(linked).data)

        elif case_update_event.action == Action.DELETE:
            case_link = get_object_or_404(
                CaseExternalEntityLink,
                case_id=case.orcabus_id,
                external_entity_id=external_entity_json["orcabus_id"],
            )

            deleted_link = unlink_case_to_external_entity_and_emit(case_link)
            logger.info(
                f"Successfully unlinked case {case.orcabus_id} from external entity {external_entity_json['orcabus_id']}"
            )

        return
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")

        raise e
