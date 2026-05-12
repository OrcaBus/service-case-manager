import logging
import os
from typing import Optional

import boto3
import requests

from app.models import Case

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
        raise RuntimeError("REDCAP_TOKEN_PARAMETER_NAME environment variable is not set.")

    ssm = boto3.client("ssm")
    response = ssm.get_parameters(Names=[REDCAP_TOKEN_PARAMETER_NAME], WithDecryption=True)

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
    http_response = requests.post(REDCAP_ENDPOINT, data=payload, timeout=REQUEST_TIMEOUT)
    if http_response.status_code == 200:
        return http_response.json()
    raise Exception(
        f"REDCap API request failed with status {http_response.status_code}: {http_response.text}"
    )


def get_redcap_record_by_date_range(after_date: Optional[str] = None, before_date: Optional[str] = None) -> list[dict]:
    """Fetch REDCap records within a given date range."""
    payload = _build_payload(dateRangeBegin=after_date, dateRangeEnd=before_date)
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
        redcap_case_type_mapping = {"1": "cttso", "2": "wgts"}
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
            logger.info(f"Updating case {request_form_id}: type {case.type} -> {case_type}")
            case.type = case_type
            case.save()
        else:
            logger.debug(f"No update needed for case {request_form_id}")
        return case
    except Case.DoesNotExist:
        logger.info(f"Creating new case {request_form_id} with type {case_type}")
        case = Case(request_form_id=request_form_id, type=case_type, study_type="clinical")
        case.save()

        return case


def upsert_redcap_records_by_date_range(after_date: str, before_date: Optional[str] = None) -> dict:
    """Fetch records from REDCap by date range and upsert them into the Case model.

    Processes all records, logging individual failures without aborting the batch.

    Returns a dict with 'synced' and 'failed' counts.
    """
    records = get_redcap_record_by_date_range(after_date=after_date, before_date=before_date)

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
