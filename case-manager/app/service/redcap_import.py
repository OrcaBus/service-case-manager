import logging
import os
import boto3
import requests

from functools import partial
from typing import Optional
from datetime import datetime, date, time, timezone, timedelta
from zoneinfo import ZoneInfo
from django.db import transaction

from app.aws.event_bridge import emit_event
from app.models import (
    CaseExternalEntityLink,
    PendingExternalEntity,
    ExternalEntity,
)
from app.models import Case, ExternalSyncLog, State, User
from app.models.case import CaseType, CaseStudyType
from app.models.state import CaseStatus
from app.schemas.events.case_state_change_model import (
    CaseStateChange,
    Action as CaseStateAction,
    DetailType as CaseStateDetailType,
)
from app.serializers.case import CaseSerializer
from app.service.external_entity import get_or_create_entities_by_sample_id

logger = logging.getLogger(__name__)

REDCAP_ENDPOINT = "https://redcap.unimelb.edu.au/api/"
REDCAP_TOKEN_PARAMETER_NAME = os.environ.get("REDCAP_TOKEN_PARAMETER_NAME", "")
REQUEST_TIMEOUT = 30  # seconds

# System user attributed as `created_by` for states written by this import.
REDCAP_SYSTEM_USER_EMAIL = "system@orcabus.org"

# Case-sensitive study_names that get shorter turnaround for the report due date.
SHORT_TURNAROUND_STUDY_NAMES = {"ASPi2L", "OCEANiC"}
SHORT_TURNAROUND_WEEKS = 3
DEFAULT_TURNAROUND_WEEKS = 4

# Prefix used by REDCap for the rnasum_reference multi-value checkbox.
_RNASUM_REFERENCE_PREFIX = "rnasum_reference___"

# Explicit mapping from REDCap checkbox suffix to stored value.
_RNASUM_REFERENCE_MAP: dict[str, str] = {
    "pancan": "PANCAN",
    "acc": "ACC",
    "blca": "BLCA",
    "blca_net": "BLCA-NET",
    "brca": "BRCA",
    "cesc": "CESC",
    "chol": "CHOL",
    "coad": "COAD",
    "dlbc": "DLBC",
    "esca": "ESCA",
    "gbm": "GBM",
    "hnsc": "HNSC",
    "kich": "KICH",
    "kirc": "KIRC",
    "kirp": "KIRP",
    "laml": "LAML",
    "lgg": "LGG",
    "lihc": "LIHC",
    "luad": "LUAD",
    "lusc": "LUSC",
    "meso": "MESO",
    "ov": "OV",
    "paad": "PAAD",
    "pcpg": "PCPG",
    "prad": "PRAD",
    "read": "READ",
    "sarc": "SARC",
    "skcm": "SKCM",
    "stad": "STAD",
    "tgct": "TGCT",
    "thca": "THCA",
    "thym": "THYM",
    "ucec": "UCEC",
    "ucs": "UCS",
    "uvm": "UVM",
    "luad_lcnec": "LUAD-LCNEC",
    "paad_acc": "PAAD-ACC",
    "paad_ipmn": "PAAD-IPMN",
    "paad_net": "PAAD-NET",
}


_redcap_token: Optional[str] = None


def _get_redcap_token() -> str:
    """Lazily fetch and cache the REDCap API token from SSM Parameter Store."""
    global _redcap_token

    if _redcap_token:
        return _redcap_token

    if not REDCAP_TOKEN_PARAMETER_NAME:
        raise RuntimeError(
            "REDCAP_TOKEN_PARAMETER_NAME environment variable is not set."
        )

    ssm = boto3.client("ssm")
    response = ssm.get_parameters(
        Names=[REDCAP_TOKEN_PARAMETER_NAME], WithDecryption=True
    )

    parameters = response.get("Parameters", [])
    if not parameters:
        raise RuntimeError("REDCap token not found.")

    _redcap_token = parameters[0]["Value"]
    return _redcap_token


def _build_payload(**extra_fields) -> dict:
    """Build a REDCap API payload with the base fields and any extra fields."""
    return {
        "token": _get_redcap_token(),
        "content": "record",
        "action": "export",
        "format": "json",
        **extra_fields,
    }


def _post(payload: dict) -> list[dict]:
    """Send a POST request to the REDCap API and return the parsed JSON response."""
    http_response = requests.post(
        REDCAP_ENDPOINT, data=payload, timeout=REQUEST_TIMEOUT
    )
    if http_response.status_code == 200:
        return http_response.json()
    raise Exception(
        f"REDCap API request failed with status {http_response.status_code}: {http_response.text}"
    )


def get_redcap_record_by_date_range(
    after_date: Optional[str] = None, before_date: Optional[str] = None
) -> list[dict]:
    """Fetch REDCap records within a given date range."""
    extra = {}
    if after_date:
        extra["dateRangeBegin"] = after_date
    if before_date:
        extra["dateRangeEnd"] = before_date
    payload = _build_payload(**extra)
    return _post(payload)


def get_redcap_record_by_filter(filter_logic: str) -> list[dict]:
    """Fetch REDCap records matching a given REDCap filterLogic expression."""
    payload = _build_payload(filterLogic=filter_logic)
    return _post(payload)


def _get_redcap_system_user() -> User:
    """The system user attributed as `created_by` for states written by this import."""
    user, _ = User.objects.get_or_create(email=REDCAP_SYSTEM_USER_EMAIL)
    return user


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_time(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    return datetime.strptime(value, "%H:%M").time()


def _add_state_if_new(
    case: Case,
    status: CaseStatus,
    event_date: date,
    event_time: Optional[time] = None,
) -> Optional[State]:
    """
    Create a State for `case` unless one with the same status/event_date already
    exists (REDCap sync windows overlap on re-run, so this keeps it idempotent).
    """
    if State.objects.filter(case=case, status=status, event_date=event_date).exists():
        return None

    return State.objects.create(
        case=case,
        status=status,
        event_date=event_date,
        event_time=event_time,
        created_by=_get_redcap_system_user(),
    )


def _emit_case_state_change(case: Case, action: CaseStateAction) -> None:
    """Emit a CaseStateChange event to EventBridge after the transaction commits."""
    case_data = dict(CaseSerializer(case).data)
    event_model = CaseStateChange(
        action=action,
        refId=str(case.orcabus_id),
        timestamp=datetime.now(timezone.utc).isoformat(),
        case=case_data,
    )
    transaction.on_commit(
        partial(
            emit_event,
            detail_type=CaseStateDetailType.CaseStateChange.value,
            event_detail_model=event_model,
        )
    )


@transaction.atomic
def upsert_case_from_redcap_record(record: dict[str, str]) -> Case:
    """Upsert a Case from REDCap record fields."""

    request_form_id = record.get("request_id")
    if request_form_id is None:
        raise KeyError("Missing 'request_id' in REDCap record.")

    # REDCap has no concept of "research" cases — anything sourced from REDCap
    # is always clinical. Research cases are created via some other pathway.
    data: dict[str, str | bool] = {
        "request_form_id": request_form_id,
        "study_type": CaseStudyType.CLINICAL,
    }

    case_type = record.get("rf_test_requested")
    if case_type is not None:
        accepted_values = [c[0] for c in Case.type.field.choices]
        if case_type not in accepted_values:
            raise ValueError(f"Unknown rf_test_requested value: {case_type}")
        data["type"] = case_type

    study_name = record.get("rf_study")
    if study_name is not None:
        data["study_name"] = study_name

    study_id = record.get("rf_study_id")
    if study_id is not None:
        data["study_id"] = study_id

    ur_number = record.get("rf_ur")
    if ur_number is not None:
        data["ur_number"] = ur_number

    # Extract rnasum_reference from REDCap multi-value checkbox fields.
    # Unknown suffixes (not yet in _RNASUM_REFERENCE_MAP) are silently skipped.
    rnasum_references = []
    for key, value in record.items():
        if value != "1" or not key.startswith(_RNASUM_REFERENCE_PREFIX):
            continue
        suffix = key.removeprefix(_RNASUM_REFERENCE_PREFIX)
        stored_value = _RNASUM_REFERENCE_MAP.get(suffix)
        if stored_value:
            rnasum_references.append(stored_value)
    data["rnasum_references"] = rnasum_references

    # Store the entire raw REDCap record for audit and UI rendering.
    data["redcap_payload"] = record

    # 0 = False, 1 = True
    nata_accred_report = record.get("nata_accred_report")
    if nata_accred_report is not None:
        data["is_nata_accredited"] = nata_accred_report == "1"
    case, is_created, is_updated = Case.objects.update_or_create_if_needed(
        {"request_form_id": request_form_id},
        data,
        change_reason="REDCap sync",
    )

    # Add states for samples
    cttso_receipt_date = _parse_date(record.get("cttso_receipt_date"))
    if cttso_receipt_date:
        _add_state_if_new(
            case,
            CaseStatus.CTTSO_SAMPLE_RECEIVED,
            event_date=cttso_receipt_date,
            event_time=_parse_time(record.get("cttso_receipt_time")),
        )

    tumour_receipt_date = _parse_date(record.get("tumour_receipt_date"))
    if tumour_receipt_date:
        _add_state_if_new(
            case,
            CaseStatus.WGTS_TUMOUR_SAMPLE_RECEIVED,
            event_date=tumour_receipt_date,
        )

    germline_receipt_date = _parse_date(record.get("germline_receipt_date"))
    if germline_receipt_date:
        _add_state_if_new(
            case,
            CaseStatus.WGTS_GERMLINE_SAMPLE_RECEIVED,
            event_date=germline_receipt_date,
        )

    # All samples in for this case type -> add terminal intake state, dated after
    # the last contributing sample so it lands at the end of the case's states.
    all_sample_received_at = None
    if case.type == CaseType.CTTSO and cttso_receipt_date:
        all_sample_received_at = cttso_receipt_date
    elif case.type == CaseType.WGS_N and germline_receipt_date:
        all_sample_received_at = germline_receipt_date
    elif case.type == CaseType.WGTS and germline_receipt_date and tumour_receipt_date:
        all_sample_received_at = max(germline_receipt_date, tumour_receipt_date)

    if all_sample_received_at:
        _add_state_if_new(
            case,
            CaseStatus.ALL_SAMPLE_RECEIVED,
            event_date=all_sample_received_at,
        )

        # Only set once, only set if unset (possibility set manually beforehand)
        if not case.due_date:
            weeks = (
                SHORT_TURNAROUND_WEEKS
                if case.study_name in SHORT_TURNAROUND_STUDY_NAMES
                else DEFAULT_TURNAROUND_WEEKS
            )
            case.due_date = all_sample_received_at + timedelta(weeks=weeks)
            case._change_reason = "REDCap sync: due date set on all sample received"
            case.save()

    if is_created:
        logger.info(f"Created case for request_form_id={request_form_id}")
        _emit_case_state_change(case, CaseStateAction.CREATE)
    elif is_updated:
        logger.info(f"Updated case for request_form_id={request_form_id}")
        _emit_case_state_change(case, CaseStateAction.UPDATE)
    else:
        logger.debug(f"No change for case request_form_id={request_form_id}")

    return case


@transaction.atomic
def resolve_sample_links_from_redcap_record(case: Case, record: dict[str, str]) -> None:
    """
    For each sample ID found in the REDCap record:
      - If a matching ExternalEntity already exists, create a confirmed CaseExternalEntityLink.
      - Otherwise, queue a PendingExternalEntity to be resolved later by the originating microservice.
    Both operations are idempotent (get_or_create).
    """
    _CASE_TYPE_SAMPLE_FIELDS: dict[str, tuple[str, ...]] = {
        CaseType.WGTS: ("tumour_sample_id", "germline_sample_id", "wts_sample_id"),
        CaseType.CTTSO: ("cttso_sample_id",),
    }

    sample_fields = _CASE_TYPE_SAMPLE_FIELDS.get(case.type, ())
    if not sample_fields:
        logger.debug(
            "No sample field mapping for case %s type=%s",
            case.request_form_id,
            case.type,
        )
        return

    for field_name in sample_fields:
        sample_id = (record.get(field_name) or "").strip()
        if not sample_id:
            continue

        # Check if the ExternalEntity is already known (resolved by the microservice)
        external_entity = ExternalEntity.objects.filter(
            service_name="metadata",
            type="sample",
            alias=sample_id,
        ).first()

        if external_entity:
            # Entity is already resolved — create a confirmed link if not already present
            _, created = CaseExternalEntityLink.objects.get_or_create(
                case=case,
                external_entity=external_entity,
            )
            logger.info(
                "case=%s: %s ExternalEntity link for alias=%s",
                case.request_form_id,
                "created" if created else "existing",
                sample_id,
            )
        else:
            # Entity not in our DB yet — check the metadata service before queuing as pending
            sample_entity, library_entities = get_or_create_entities_by_sample_id(
                sample_id
            )

            if sample_entity or library_entities:
                # link all entities to the case
                for entity in filter(None, [sample_entity, *library_entities]):
                    _, created = CaseExternalEntityLink.objects.get_or_create(
                        case=case,
                        external_entity=entity,
                    )
                    logger.info(
                        "case=%s: %s ExternalEntity link (via metadata lookup) for alias=%s type=%s",
                        case.request_form_id,
                        "created" if created else "existing",
                        entity.alias,
                        entity.type,
                    )
            else:
                # Sample does not exist in the metadata service yet — queue for later resolution
                _, created = PendingExternalEntity.objects.get_or_create(
                    case=case,
                    service_name="metadata",
                    type="sample",
                    alias=sample_id,
                )
                logger.info(
                    "case=%s: %s PendingExternalEntity for alias=%s",
                    case.request_form_id,
                    "queued" if created else "already pending",
                    sample_id,
                )


def upsert_redcap_records_by_date_range(
    after_date: str, before_date: Optional[str] = None
) -> dict:
    """Fetch records from REDCap by date range and upsert them into the Case model.

    Processes all records, logging individual failures without aborting the batch.

    Returns a dict with 'synced' and 'failed' counts.
    """
    records = get_redcap_record_by_date_range(
        after_date=after_date, before_date=before_date
    )

    synced = 0
    failed = 0
    for record in records:
        try:
            case = upsert_case_from_redcap_record(record)
            resolve_sample_links_from_redcap_record(case, record)
            synced += 1
        except Exception as e:
            logger.error(f"Failed to upsert record {record}: {e}")
            failed += 1

    return {"synced": synced, "failed": failed}


@transaction.atomic
def auto_sync_redcap_records():
    """
    Automatically sync redcap records using REDCap API, where the range is taken
    """
    # Confirmed with REDCap administrator that server time query is based on AEST/AEDT (switching when appropriate)
    melbourne_tz = ZoneInfo("Australia/Melbourne")
    redcap_datetime_fmt = "%Y-%m-%d %H:%M:%S"

    # Will start the beginning range date from the last import
    last_import = (
        ExternalSyncLog.objects.filter(external_service="redcap")
        .order_by("-imported_at")
        .first()
    )
    after_date = (
        last_import.imported_at.astimezone(melbourne_tz).strftime(redcap_datetime_fmt)
        if last_import
        else None
    )

    # Get the current datetime minus 1 minute buffer
    current_datetime = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).replace(  # buffer 1 minute to avoid race condition with new records
        second=0, microsecond=0
    )  # rundown to nearest 00
    before_date = current_datetime.astimezone(melbourne_tz).strftime(
        redcap_datetime_fmt
    )

    result = upsert_redcap_records_by_date_range(
        after_date=after_date, before_date=before_date
    )
    ExternalSyncLog.objects.create(
        external_service="redcap", imported_at=current_datetime
    )

    return result
