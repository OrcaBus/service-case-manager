from django.db import transaction

from app.aws.event_bridge import emit_event
from app.models import Case, CaseExternalEntityLink, ExternalEntity, User, CaseUserLink
from app.schemas.events.case_srelationship_state_change_model import (
    CaseRelationshipStateChange,
    Action,
    DetailType,
)
from app.serializers import CaseSerializer
from app.serializers import ExternalEntitySerializer


@transaction.atomic
def link_case_to_external_entity_and_emit(
    case: Case, external_entity: ExternalEntity, added_via: str = "manual"
) -> CaseExternalEntityLink:
    """
    Save the case-external entity relationship and emit an event to the Event Bridge.
    """

    case_entity_link = CaseExternalEntityLink.objects.create(
        case=case, external_entity=external_entity, added_via=added_via
    )

    case_data = CaseSerializer(case_entity_link.case).data
    external_entity_data = ExternalEntitySerializer(
        case_entity_link.external_entity
    ).data

    relationship_change_event = CaseRelationshipStateChange(
        action=Action.CREATE,
        refId=str(case_entity_link.id),
        addedVia=added_via,
        timestamp=case_entity_link.timestamp.isoformat(),
        case=case_data,
        externalEntity=external_entity_data,
    )

    # emit event to Event Bridge
    emit_event(
        detail_type=DetailType.CaseRelationshipStateChange.value,
        event_detail_model=relationship_change_event,
    )
    return case_entity_link


@transaction.atomic
def unlink_case_to_external_entity_and_emit(
    case_external_entity: CaseExternalEntityLink,
) -> CaseExternalEntityLink:
    """
    Remove the case-external entity relationship and emit an event to the Event Bridge.
    """
    case_data = CaseSerializer(case_external_entity.case).data
    external_entity_data = ExternalEntitySerializer(
        case_external_entity.external_entity
    ).data

    relationship_change_event = CaseRelationshipStateChange(
        action=Action.DELETE,
        refId=str(case_external_entity.id),
        addedVia=case_external_entity.added_via,
        timestamp=case_external_entity.timestamp.isoformat(),
        case=case_data,
        externalEntity=external_entity_data,
    )

    # Delete and send events
    case_external_entity.delete()
    emit_event(
        detail_type=DetailType.CaseRelationshipStateChange.value,
        event_detail_model=relationship_change_event,
    )
    return case_external_entity
