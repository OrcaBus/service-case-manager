import os
import json
import logging
import django
import boto3

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist

from app.service.external_entity import get_or_create_external_entity
from app.service.case import link_case_to_external_entity_and_emit
from app.models import (
    Case,
    ExternalEntity,
    PendingExternalEntity,
    CaseExternalEntityLink,
)
from app.serializers.case import CaseExternalEntityLinkCreateSerializer

logger = logging.getLogger()
logger.setLevel(logging.INFO)

QUEUE_URL = os.environ.get("METADATA_MANAGER_LINKING_QUEUE_URL")
# SQS enforces a hard 43200s (12h) ceiling on total visibility timeout measured from
# first receipt, not from the ChangeMessageVisibility call. Subtracting the Lambda
# timeout (15 min = 900s) ensures we never breach the limit regardless of when during
# execution the call is made.
VISIBILITY_TIMEOUT_RETRY_SECONDS = 12 * 60 * 60 - 15 * 60  # ~11h 45m

sqs = boto3.client("sqs")


def _upsert_library_external_entity(
    library_orcabus_id: str, library_id: str
) -> ExternalEntity:
    """
    Upsert a library ExternalEntity directly from payload fields (no HTTP call).
    Prefix is inferred from the orcabusId (e.g. 'lib' from 'lib.abc123').
    """
    prefix = library_orcabus_id.split(".")[0] if "." in library_orcabus_id else None
    library_entity, created = ExternalEntity.objects.update_or_create(
        orcabus_id=library_orcabus_id,
        defaults={
            "prefix": prefix,
            "type": "library",
            "service_name": "metadata",
            "alias": library_id,
        },
    )
    action = "Created" if created else "Updated"
    logger.info(
        f"{action} library ExternalEntity: {library_orcabus_id} (alias={library_id})"
    )
    return library_entity


def _link_entity_to_case(case: Case, entity: ExternalEntity, label: str) -> None:
    """Link an ExternalEntity to a Case, logging a warning if it is already linked."""
    try:
        link = link_case_to_external_entity_and_emit(
            case, entity, history_user="system"
        )
        logger.info(
            f"Linked {label} '{entity.alias}' ({entity.orcabus_id}) to case '{case.orcabus_id}'"
        )
        logger.info(f"Link data: {CaseExternalEntityLinkCreateSerializer(link).data}")
    except IntegrityError:
        logger.warning(
            f"{label.capitalize()} '{entity.alias}' ({entity.orcabus_id}) is already linked "
            f"to case '{case.orcabus_id}', skipping."
        )


def _process_sample_based_linking(data: dict) -> None:
    """
    Fallback path: no requestFormId — resolve the case via sample.sampleId.

    Steps:
    1. Look up sample.sampleId in ExternalEntity (already resolved) and/or
       PendingExternalEntity (waiting for orcabusId).
    2. If found in PendingExternalEntity, promote it to a real ExternalEntity
       using sample.orcabusId and link the sample to the pending record's case.
    3. Upsert the library ExternalEntity from payload fields and link it to
       every case resolved in step 1/2.
    """
    library_orcabus_id = data.get("orcabusId")
    library_id = data.get("libraryId")
    sample_data = data.get("sample", {})
    sample_id = sample_data.get("sampleId")
    sample_orcabus_id = sample_data.get("orcabusId")

    if not sample_id:
        logger.warning(
            f"Skipping message: no requestFormId and no sample.sampleId in data: {data}"
        )
        return

    if not library_orcabus_id or not library_id:
        logger.warning(
            f"Skipping message: missing library orcabusId or libraryId in data: {data}"
        )
        return

    # (alias, service_name, type) is unique — at most one record expected in each table.
    # Raise immediately if we ever find more than one; that indicates a data integrity issue.
    resolved_qs = ExternalEntity.objects.filter(
        alias=sample_id, service_name="metadata", type="sample"
    )
    if resolved_qs.count() > 1:
        raise ValueError(
            f"Data integrity violation: multiple ExternalEntity records found for "
            f"sample alias='{sample_id}', service_name='metadata', type='sample'. "
            f"Expected at most one."
        )
    resolved_sample_entity = resolved_qs.first()

    pending_qs = PendingExternalEntity.objects.filter(
        alias=sample_id, service_name="metadata", type="sample"
    )
    if pending_qs.count() > 1:
        raise ValueError(
            f"Data integrity violation: multiple PendingExternalEntity records found for "
            f"sample alias='{sample_id}', service_name='metadata', type='sample'. "
            f"Expected at most one."
        )
    pending_sample_entity = pending_qs.select_related("case").first()

    if not resolved_sample_entity and not pending_sample_entity:
        raise ObjectDoesNotExist(
            f"Sample '{sample_id}' not found in ExternalEntity or PendingExternalEntity — "
            f"case not ready yet, will retry."
        )

    case: Case | None = None

    # --- Path A: sample already fully resolved — find its linked case ---
    if resolved_sample_entity:
        case_link = (
            CaseExternalEntityLink.objects.filter(
                external_entity=resolved_sample_entity
            )
            .select_related("case")
            .first()
        )
        if case_link:
            case = case_link.case
        else:
            logger.warning(
                f"Sample ExternalEntity '{sample_id}' exists but is not linked to any case — skipping."
            )
            return

    # --- Path B: sample still pending — promote to ExternalEntity and link ---
    elif pending_sample_entity:
        if not sample_orcabus_id:
            logger.warning(
                f"Cannot promote PendingExternalEntity for sample '{sample_id}': "
                f"no sample.orcabusId in payload — skipping pending promotion."
            )
            return

        sample_prefix = (
            sample_orcabus_id.split(".")[0] if "." in sample_orcabus_id else None
        )
        resolved_sample_entity, created = ExternalEntity.objects.get_or_create(
            orcabus_id=sample_orcabus_id,
            defaults={
                "prefix": sample_prefix,
                "type": "sample",
                "service_name": "metadata",
                "alias": sample_id,
            },
        )
        if created:
            logger.info(
                f"Promoted sample '{sample_id}' to ExternalEntity {sample_orcabus_id}"
            )

        case = pending_sample_entity.case
        _link_entity_to_case(case, resolved_sample_entity, label="sample")

        pending_sample_entity.delete()
        logger.info(
            f"Deleted PendingExternalEntity for sample '{sample_id}' on case '{case.orcabus_id}'"
        )

    # Upsert library ExternalEntity from payload and link to the resolved case
    library_entity = _upsert_library_external_entity(library_orcabus_id, library_id)
    _link_entity_to_case(case, library_entity, label="library")


def process_record(body: dict) -> None:
    """Process a single SQS message body (EventBridge event envelope)."""
    data = body.get("detail", {}).get("data", {})

    library_orcabus_id = data.get("orcabusId")
    request_form_id = data.get("requestFormId")

    # --- Path 1: requestFormId-based linking (original behaviour) ---
    if request_form_id and request_form_id != "nan":
        if not library_orcabus_id:
            logger.warning(
                f"Skipping message: requestFormId present but no orcabusId in data: {data}"
            )
            return

        case = Case.objects.get(
            request_form_id=request_form_id
        )  # raises ObjectDoesNotExist

        external_entity = get_or_create_external_entity(library_orcabus_id)

        try:
            link = link_case_to_external_entity_and_emit(
                case, external_entity, history_user="system"
            )
            logger.info(
                f"Successfully linked '{library_orcabus_id}' to case '{case.orcabus_id}'"
            )
            logger.info(
                f"Link data: {CaseExternalEntityLinkCreateSerializer(link).data}"
            )
        except IntegrityError:
            logger.warning(
                f"Library '{library_orcabus_id}' is already linked to case '{case.orcabus_id}', skipping."
            )
        return

    # --- Path 2: sample-based linking (requestFormId absent or "nan") ---
    _process_sample_based_linking(data)


def handler(event, context):
    """
    Lambda handler invoked by SQS event source mapping (batchSize=1).

    Flow:
    - EventBridge delivers MetadataStateChange events → SQS queue → this Lambda.
    - Success / already linked / invalid message: returns normally → SQS auto-deletes.
    - ObjectDoesNotExist (case not ready yet): extends visibility to ~11h45m then raises →
        SQS keeps the message and redelivers later. After maxReceiveCount failures → DLQ.
    - Unexpected errors: raises → SQS retries via default policy, then DLQ.
    """
    records = event.get("Records", [])
    logger.info(f"Received {len(records)} SQS record(s)")

    if len(records) != 1:
        raise ValueError(
            f"Expected exactly 1 SQS record (batchSize=1 is required), got {len(records)}. "
            "Check the SQS event source mapping configuration."
        )

    for record in records:
        receipt_handle = record["receiptHandle"]
        message_id = record.get("messageId", "unknown")

        logger.info(
            f"[{message_id}] Processing SQS record: {json.dumps(record, default=str)}"
        )

        try:
            body = json.loads(record["body"])
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[{message_id}] Malformed message body, skipping: {e}")
            continue

        try:
            process_record(body)
            logger.info(f"[{message_id}] Successfully processed")

        except ObjectDoesNotExist:
            logger.warning(
                f"[{message_id}] Case not found yet — extending visibility to {VISIBILITY_TIMEOUT_RETRY_SECONDS}s for "
                f"retry"
            )
            if not QUEUE_URL:
                raise RuntimeError(
                    "METADATA_MANAGER_LINKING_QUEUE_URL environment variable is not set"
                )
            sqs.change_message_visibility(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=VISIBILITY_TIMEOUT_RETRY_SECONDS,
            )
            raise  # Prevents SQS from auto-deleting; message reappears after 12h.

        except Exception as e:
            logger.error(f"[{message_id}] Unexpected error: {e}")
            raise
