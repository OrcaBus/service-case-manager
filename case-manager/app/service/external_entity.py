from django.http import Http404
from app.models import ExternalEntity
from django.core.exceptions import ObjectDoesNotExist
import requests
import os
import logging
from app.service.utils import get_service_jwt

logger = logging.getLogger(__name__)


def fetch_external_entity_data(orcabus_id: str):
    """
    Query the metadata and/or workflow service to get entity details.

    Supports:
    - Prefixed IDs: wfr.* (workflow), lib.* (library)
    - Unprefixed IDs: tries workflow first, then metadata

    Returns:
        Tuple of (service_name, entity_data_dict)

    Raises:
        Http404: When entity not found in any service
    """
    jwt_token = get_service_jwt()
    headers = {"Authorization": f"Bearer {jwt_token}"}

    domain_name = os.environ["HOSTED_ZONE_NAME"]

    # Determine which services to check based on prefix
    if orcabus_id.startswith("wfr."):
        services = [
            (
                "workflow",
                f"https://workflow.{domain_name}/api/v1/workflowrun/{orcabus_id}",
            )
        ]
    elif orcabus_id.startswith("lib."):
        services = [
            ("metadata", f"https://metadata.{domain_name}/api/v1/library/{orcabus_id}")
        ]
    else:
        # No prefix: try both services (workflow first)
        services = [
            (
                "workflow",
                f"https://workflow.{domain_name}/api/v1/workflowrun/{orcabus_id}",
            ),
            ("metadata", f"https://metadata.{domain_name}/api/v1/library/{orcabus_id}"),
        ]

    # Try each service
    for service_name, url in services:
        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return service_name, response.json()
            elif response.status_code == 404:
                continue  # Try next service
            else:
                logger.warning(
                    f"{service_name} service returned {response.status_code} for {orcabus_id}"
                )
        except requests.RequestException as e:
            logger.error(f"{service_name} service request failed for {orcabus_id}: {e}")

    # Not found in any service
    raise Http404(f"No ExternalEntity matches the given orcabus_id: {orcabus_id}")


def get_or_create_sequence_run_entity(sequence_run_id: str) -> ExternalEntity:
    """
    Get or create an ExternalEntity for a sequence run identified by its sequenceRunId.

    The sequenceRunId from the event payload is NOT the orcabus_id. This function
    queries the sequence service to resolve the real orcabusId, then gets or creates
    the corresponding ExternalEntity.

    Args:
        sequence_run_id: The sequenceRunId from the event (e.g. "r.uY6hEBUmv5x5XUDhkNVxtY").

    Returns:
        The existing or newly created ExternalEntity for the sequence run.

    Raises:
        Http404: When the sequence run is not found in the sequence service.
    """
    # Fast path: entity already exists (keyed by alias + type)
    try:
        return ExternalEntity.objects.get(alias=sequence_run_id, type="sequence_run")
    except ObjectDoesNotExist:
        pass

    # Query the sequence service to resolve the real orcabusId
    jwt_token = get_service_jwt()
    headers = {"Authorization": f"Bearer {jwt_token}"}
    domain_name = os.environ["HOSTED_ZONE_NAME"]
    url = f"https://sequence.{domain_name}/api/v1/sequencerun/"

    try:
        response = requests.get(
            url, headers=headers, params={"sequenceRunId": sequence_run_id}
        )
    except requests.RequestException as e:
        logger.error(
            f"Sequence service request failed for sequenceRunId '{sequence_run_id}': {e}"
        )
        raise Http404(
            f"Sequence service unreachable for sequenceRunId: {sequence_run_id}"
        )

    if response.status_code != 200:
        raise Http404(
            f"Sequence service returned {response.status_code} for sequenceRunId '{sequence_run_id}'"
        )

    data = response.json()
    results = data.get("results")
    if not results or len(results) != 1:
        raise Http404(
            f"Sequence run is not equal to one for sequenceRunId: {sequence_run_id}"
        )

    orcabus_id = results[0].get("orcabusId")
    if not orcabus_id:
        raise Http404(
            f"Sequence service response missing 'orcabusId' for sequenceRunId: {sequence_run_id}"
        )

    external_entity = ExternalEntity.objects.create(
        orcabus_id=orcabus_id,
        prefix=orcabus_id.split(".")[0] if "." in orcabus_id else "",
        type="sequence_run",
        service_name="sequence",
        alias=sequence_run_id,
    )
    logger.info(f"Created sequence run external entity: {sequence_run_id}")
    return external_entity


def get_or_create_external_entity(external_entity_orcabus_id: str) -> ExternalEntity:
    """
    Get or create external entity by orcabus_id.

    Creates the entity by looking it up in the appropriate service based on the orcabus_id prefix:
      prefix wfr. -> workflow run (workflow service)
      prefix lib. -> library (metadata service)

    For sequence runs, use get_or_create_sequence_run_entity() instead.
    """
    try:
        external_entity = ExternalEntity.objects.get(
            orcabus_id=external_entity_orcabus_id
        )
        return external_entity
    except ObjectDoesNotExist:
        service, entity_data = fetch_external_entity_data(external_entity_orcabus_id)

        if service == "workflow":
            external_entity = ExternalEntity.objects.create(
                orcabus_id=external_entity_orcabus_id,
                prefix="wfr",
                type="workflow_run",
                service_name="workflow",
                alias=entity_data.get("portalRunId"),
            )
            logger.info(
                f"Created workflow run external entity: {external_entity_orcabus_id}"
            )
            return external_entity
        elif service == "metadata":
            external_entity = ExternalEntity.objects.create(
                orcabus_id=external_entity_orcabus_id,
                prefix="lib",
                type="library",
                service_name="metadata",
                alias=entity_data.get("libraryId"),
            )
            logger.info(
                f"Created library external entity: {external_entity_orcabus_id}"
            )
            return external_entity

        logger.error(
            f"Unknown service type '{service}' for external entity: {external_entity_orcabus_id}"
        )
        raise Http404("No ExternalEntity matches the given the orcabus_id.")
