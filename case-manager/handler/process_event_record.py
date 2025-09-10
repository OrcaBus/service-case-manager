import django
import os
import logging
import json

from django.shortcuts import get_object_or_404
from app.models import Case, ExternalEntity
from app.schemas.events.case_relationship_update_model import CaseRelationshipUpdate, Action, DetailType
from app.serializers.case import CaseExternalEntityLinkSerializer
from app.service.case import link_case_to_external_entity_and_emit

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings.base')
django.setup()

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info(f"Processing event: {json.dumps(event)}")

    try:
        case_update_event = CaseRelationshipUpdate(**event)

        case = get_object_or_404(Case, pk=case_update_event.case['orcabus_id'])

        external_entity_json = case_update_event.externalEntity
        external_entity, _is_created = ExternalEntity.objects.get_or_create(
            orcabus_id=case_update_event.externalEntity['orcabus_id'],
            defaults=external_entity_json)

        linked = link_case_to_external_entity_and_emit(case=case,
                                                       external_entity=external_entity,
                                                       added_via=case_update_event.addedVia)

        logger.info(f"Successfully linked case {case.orcabus_id} to external entity {external_entity.orcabus_id}")
        logger.info(CaseExternalEntityLinkSerializer(linked).data)

        return
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")

        raise e
