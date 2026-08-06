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
    - Prefixed IDs: wfr.* (workflow), lib.* (library), seq.* (sequence)
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
    elif orcabus_id.startswith("seq."):
        services = [
            (
                "sequence",
                f"https://sequence.{domain_name}/api/v1/sequence_run/{orcabus_id}/",
            )
        ]
    else:
        # No prefix: try both services (workflow first)
        services = [
            (
                "workflow",
                f"https://workflow.{domain_name}/api/v1/workflowrun/{orcabus_id}",
            ),
            ("metadata", f"https://metadata.{domain_name}/api/v1/library/{orcabus_id}"),
            (
                "sequence",
                f"https://sequence.{domain_name}/api/v1/sequence_run/{orcabus_id}/",
            ),
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
    url = f"https://sequence.{domain_name}/api/v1/sequence_run/"

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


def get_or_create_entities_by_sample_id(
    sample_id: str,
) -> tuple[ExternalEntity | None, list[ExternalEntity] | None]:
    """
    Query the metadata service for a sample by sampleId, then get or create ExternalEntity
    records for the sample and all libraries in its librarySet.

    This mirrors the data shape used by the metadata_manager_linking handler:
      - sample   → type="sample",  service_name="metadata", alias=sampleId
      - libraries → type="library", service_name="metadata", alias=libraryId (one per librarySet entry)

    Returns (sample_entity, library_entities) where library_entities is a (possibly empty)
    list of ExternalEntity records — one per entry in librarySet.
    Returns (None, []) when the sample is not found (caller should queue a PendingExternalEntity).
    """
    jwt_token = get_service_jwt()
    headers = {"Authorization": f"Bearer {jwt_token}"}
    domain_name = os.environ["HOSTED_ZONE_NAME"]
    url = f"https://metadata.{domain_name}/api/v1/sample/"

    try:
        response = requests.get(url, headers=headers, params={"sampleId": sample_id})
    except requests.RequestException as e:
        logger.error(
            f"Metadata service request failed while looking up sampleId '{sample_id}': {e}"
        )
        return None, []

    if response.status_code == 404 or (
        response.status_code == 200 and not response.json().get("results")
    ):
        logger.debug(f"No sample found in metadata service for sampleId '{sample_id}'")
        return None, []

    if response.status_code != 200:
        logger.warning(
            f"Metadata service returned {response.status_code} for sampleId '{sample_id}'"
        )
        return None, []

    results = response.json()["results"]
    if len(results) > 1:
        return None, None

    sample_data = results[0]
    sample_orcabus_id = sample_data.get("orcabusId")

    # --- sample entity ---
    sample_entity = None
    if sample_orcabus_id:
        sample_entity, created = ExternalEntity.objects.get_or_create(
            orcabus_id=sample_orcabus_id,
            defaults={
                "prefix": sample_orcabus_id.split(".")[0] if "." in sample_orcabus_id else "",
                "type": "sample",
                "service_name": "metadata",
                "alias": sample_data.get("sampleId", sample_id),
            },
        )
        if created:
            logger.info(
                f"Created sample ExternalEntity for sampleId='{sample_id}' orcabusId='{sample_orcabus_id}'"
            )

    # --- library entities (one per librarySet entry) ---
    library_entities: list[ExternalEntity] = []
    for library_data in sample_data.get("librarySet", []):
        library_orcabus_id = library_data.get("orcabusId")
        library_id = library_data.get("libraryId")
        if not library_orcabus_id:
            logger.warning(
                f"Skipping librarySet entry missing orcabusId for sampleId='{sample_id}': {library_data}"
            )
            continue
        library_entity, created = ExternalEntity.objects.get_or_create(
            orcabus_id=library_orcabus_id,
            defaults={
                "prefix": library_orcabus_id.split(".")[0] if "." in library_orcabus_id else "",
                "type": "library",
                "service_name": "metadata",
                "alias": library_id,
            },
        )
        if created:
            logger.info(
                f"Created library ExternalEntity for libraryId='{library_id}' orcabusId='{library_orcabus_id}'"
            )
        library_entities.append(library_entity)

    return sample_entity, library_entities


def get_or_create_external_entity(external_entity_orcabus_id: str) -> ExternalEntity:
    """
    Get or create external entity by orcabus_id.

    Creates the entity by looking it up in the appropriate service based on the orcabus_id prefix:
      prefix wfr. -> workflow_run run (workflow service)
      prefix lib. -> library (metadata service)
      prefix seq. -> sequence_run (sequence service)

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
        elif service == "sequence":
            external_entity = ExternalEntity.objects.create(
                orcabus_id=external_entity_orcabus_id,
                prefix="seq",
                type="sequence_run",
                service_name="sequence",
                alias=entity_data.get("sequenceRunId"),
            )
            logger.info(
                f"Created library external entity: {external_entity_orcabus_id}"
            )
            return external_entity

        logger.error(
            f"Unknown service type '{service}' for external entity: {external_entity_orcabus_id}"
        )
        raise Http404("No ExternalEntity matches the given the orcabus_id.")
