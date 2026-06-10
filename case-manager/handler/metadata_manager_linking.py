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
from app.models import Case
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


def process_record(body: dict) -> None:
    """Process a single SQS message body (EventBridge event envelope)."""
    data = body.get("detail", {}).get("data", {})

    library_orcabus_id = data.get("orcabusId")
    request_form_id = data.get("requestFormId")

    if not library_orcabus_id or not request_form_id or request_form_id == "nan":
        logger.warning(
            f"Skipping message: no valid 'orcabusId' or 'requestFormId' in data: {data}"
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
        logger.info(f"Link data: {CaseExternalEntityLinkCreateSerializer(link).data}")
    except IntegrityError:
        logger.warning(
            f"Library '{library_orcabus_id}' is already linked to case '{case.orcabus_id}', skipping."
        )


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
