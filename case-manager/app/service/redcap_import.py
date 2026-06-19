import logging
import os
import boto3
import requests

from typing import Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from django.db import transaction

from app.models import (
    Case,
    CaseExternalEntityLink,
    ExternalSyncLog,
    PendingExternalEntity,
    ExternalEntity,
)
from app.models.case import CaseType

logger = logging.getLogger(__name__)


REDCAP_ENDPOINT = "https://redcap.unimelb.edu.au/api/"
REDCAP_TOKEN_PARAMETER_NAME = os.environ.get("REDCAP_TOKEN_PARAMETER_NAME", "")
REQUEST_TIMEOUT = 30  # seconds

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
        "fields[0]": "request_id",
        "fields[1]": "rf_test_requested",
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


def get_case_value(field_name: str, record: dict[str, str]) -> str:
    """Extract a case field value from a REDCap record."""
    if field_name == "request_form_id":
        if "request_id" not in record:
            raise KeyError("Missing 'request_id' in REDCap record.")
        return record["request_id"]
    if field_name == "case_type":
        rf_val = record.get("rf_test_requested")
        if rf_val is None:
            raise KeyError("Missing 'rf_test_requested' in REDCap record.")
        accepted_values = [c[0] for c in Case.type.field.choices]
        if rf_val not in accepted_values:
            raise ValueError(f"Unknown rf_test_requested value: {rf_val}")
        return rf_val

    if field_name not in record:
        raise KeyError(f"Missing '{field_name}' in REDCap record.")
    return record[field_name]


def upsert_case_from_redcap_record(record: dict[str, str]) -> Case:
    """Upsert a Case from REDCap record fields."""

    request_form_id = get_case_value("request_form_id", record)
    case_type = get_case_value("case_type", record)
    payload = record

    try:
        case = Case.objects.get(request_form_id=request_form_id)

        changed = False
        if case.type != case_type:
            case.type = case_type
            changed = True

        # persist latest source snapshot (recommended for audit/debug)
        if case.redcap_payload != payload:
            case.redcap_payload = payload
            changed = True

        if changed:
            case.save()
        return case

    except Case.DoesNotExist:
        logger.info(f"Creating new case {request_form_id} with type {case_type}")
        case = Case(
            request_form_id=request_form_id,
            type=case_type,
            study_type="clinical",
            redcap_payload=payload,
        )
        case.save()

        return case


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
            # Entity not yet known — queue a pending link for later resolution
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
