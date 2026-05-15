import logging
import os
import boto3
import requests

from typing import Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from django.db import transaction

from app.models import Case, ExternalSyncLog

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
        # ⚠️ MANUAL MAPPING — verify against REDCap `rf_test_requested` field before any schema changes.
        # Last verified: 2026-05-15
        redcap_case_type_mapping = {
            "1": "cttso",  # ctTSO assay
            "2": "wgts",  # WGTS assay
            "3": "wgs_n",  # WGS Normal assay
        }
        rf_val = record.get("rf_test_requested")
        if rf_val not in redcap_case_type_mapping:
            raise ValueError(f"Unknown rf_test_requested value: {rf_val}")
        return redcap_case_type_mapping[rf_val]
    raise Exception(f"Unknown field {field_name}")


def upsert_case_from_redcap_record(record: dict[str, str]) -> Case:
    """Upsert a Case from REDCap record fields."""

    request_form_id = get_case_value("request_form_id", record)
    case_type = get_case_value("case_type", record)

    try:
        case = Case.objects.get(request_form_id=request_form_id)
        if case.type != case_type:
            logger.info(
                f"Updating case {request_form_id}: type {case.type} -> {case_type}"
            )
            case.type = case_type
            case.save()
        else:
            logger.debug(f"No update needed for case {request_form_id}")
        return case
    except Case.DoesNotExist:
        logger.info(f"Creating new case {request_form_id} with type {case_type}")
        case = Case(
            request_form_id=request_form_id, type=case_type, study_type="clinical"
        )
        case.save()

        return case


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
            upsert_case_from_redcap_record(record)
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
