import os
import logging
import requests
from typing import Literal
from django.db import transaction

from app.models import ExternalEntity, Case, CaseExternalEntityLink
from app.service.utils import get_service_jwt, get_first_two_digits

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

jwt = os.environ.get("JWT") or get_service_jwt()
headers = {"Authorization": f"Bearer {jwt}"}


@transaction.atomic
def create_case_from_library_findings(case_type: Literal["cttso", "wgts"] = None, library_id_array: list[str] = None):
    """
    Query the library API to retrieve libraries, then for each, query associated workflows and analyses for years 2024 and 2025.
    """

    if case_type == "cttso" or case_type is None:
        create_cttso_cases(library_id_array=library_id_array)
    if case_type == "wgts" or case_type is None:
        create_wgts_cases(library_id_array=library_id_array)


def get_library_request(query_params: str) -> list[dict]:
    """
    Get libraries from the metadata service based on query parameters. Only returns libraries from years 24 and 25.
    """
    base_url = f"https://metadata.{os.environ.get("DOMAIN_NAME").rstrip("/")}"
    library_url = f"{base_url}/api/v1/library/?{query_params}&ordering=-orcabus_id&rowsPerPage=100"
    libraries = []

    while True:
        logger.info(f"Querying: {library_url}")
        response = requests.get(library_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        for lib in results:
            library_id = lib.get("libraryId")
            if get_first_two_digits(library_id) not in ["24", "25"]:
                logger.info("No more results matching year 24 or 25")
                break
            libraries.append({
                "library_id": library_id,
                "orcabus_id": lib.get("orcabusId")[-26:],
                "type": lib.get("type"),
                "assay": lib.get("assay"),
            })

        next_page = data.get("links", {}).get("next")
        if not next_page:
            logger.info(f"No more results for {library_url}")
            break
        library_url = next_page

    return libraries


def get_workflow_run_request(query_params: str) -> list[dict]:
    """
    Get workflow runs from the workflow service based on query parameters.
    """
    base_url = os.environ.get("WORKFLOW_BASE_URL").rstrip("/")
    workflow_url = f"{base_url}/api/v1/workflowrun/?{query_params}&ordering=-orcabus_id&rowsPerPage=100"
    workflow_runs = []

    while True:
        logger.info(f"Querying: {workflow_url}")
        response = requests.get(workflow_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        for wfr in results:
            workflow_runs.append({
                "orcabus_id": wfr.get("orcabusId")[-26:],
                "prefix": "wfr",
                "type": "workflow_run",
                "service_name": "workflow",
                "alias": wfr.get("portalRunId"),
            })

        next_page = data.get("links", {}).get("next")
        if not next_page:
            logger.info(f"No more results for {workflow_url}")
            break
        workflow_url = next_page

    return workflow_runs


def get_workflow_run_detail(orcabus_id: str) -> dict:
    """
    Get workflow run details for a specific orcabus_id.
    """
    base_url = f"https://workflow.{os.environ.get("DOMAIN_NAME").rstrip("/")}"
    workflow_url = f"{base_url}/api/v1/workflowrun/{orcabus_id}/"
    logger.info(f"Querying detail: {orcabus_id}")

    response = requests.get(workflow_url, headers=headers)
    response.raise_for_status()
    return response.json()


def create_cttso_cases(library_id_array: list[str] = None):
    """
    Create ctTSO cases from ctDNA libraries (manual retrospective).
    """
    logger.info("Creating ctTSO cases")
    if library_id_array:
        query_params = "&".join([f"libraryId={lib_id}" for lib_id in library_id_array])
    else:
        query_params = "phenotype=tumor&type=ctDNA"

    libraries = get_library_request(query_params)

    workflow_names = [
        "dragen-tso500-ctdna",
        "pieriandx-tso500-ctdna",
        "cttsov2",
        "pieriandx"
    ]

    for lib in libraries:
        library_id = lib["library_id"]
        orcabus_id = lib["orcabus_id"]

        case, is_new = Case.objects.get_or_create(
            external_entity_set__orcabus_id=orcabus_id,
            defaults={
                "title": f"cttso-{library_id}",
                "description": "retrospective case (auto-generated)"
            }
        )

        # Only proceed if the case has more than just the library linked as an external entity
        if not is_new and case.external_entity_set.count() > 1:
            logger.info(f"Library {library_id} already has a linked case, skipping.")
            continue

        # Link the library as an external entity
        lib_entity, _ = ExternalEntity.objects.get_or_create(
            orcabus_id=orcabus_id,
            defaults={
                "prefix": "lib",
                "type": "library",
                "service_name": "metadata",
                "alias": library_id
            }
        )
        CaseExternalEntityLink.objects.get_or_create(case=case, external_entity=lib_entity)

        workflow_query = [f"libraries__library_id={library_id}"] + [f"workflow__name={name}" for name in workflow_names]
        workflow_runs = get_workflow_run_request("&".join(workflow_query))

        for workflow_run in workflow_runs:
            wfr_orcabus_id = workflow_run["orcabus_id"]
            wfr_entity, _ = ExternalEntity.objects.get_or_create(
                orcabus_id=wfr_orcabus_id,
                defaults={
                    "prefix": workflow_run["prefix"],
                    "type": workflow_run["type"],
                    "service_name": workflow_run["service_name"],
                    "alias": workflow_run["alias"]
                }
            )
            CaseExternalEntityLink.objects.get_or_create(case=case, external_entity=wfr_entity)


def create_wgts_cases(library_id_array: list[str] = None):
    """
    Create WGTS tumor-normal cases from WGS libraries (manual retrospective).
    """
    logger.info("Creating WGTS tumor-normal cases")

    if library_id_array:
        query_params = "&".join([f"libraryId={lib_id}" for lib_id in library_id_array])
    else:
        query_params = "phenotype=tumor&type=WGS"

    libraries = get_library_request(query_params)

    workflow_names = [
        "oncoanalyser-wgts-dna-rna",
        "rnasum",
        "umccrise",
        "tumor-normal",
        "oncoanalyser-wgts-dna",
        "dragen-wgts-dna",
        "sash"
    ]

    for lib in libraries:
        library_id = lib["library_id"]
        orcabus_id = lib["orcabus_id"]

        case, is_new = Case.objects.get_or_create(
            external_entity_set__orcabus_id=orcabus_id,
            defaults={
                "title": f"ctdna-{library_id}",
                "description": "retrospective case (auto-generated)"
            }
        )
        # Only proceed if the case has more than just the library linked as an external entity
        if not is_new and case.external_entity_set.count() > 1:
            logger.info(f"Library {library_id} already has a linked case, skipping.")
            continue

        workflow_query = [f"libraries__library_id={library_id}"] + [f"workflow__name={name}" for name in workflow_names]
        workflow_runs = get_workflow_run_request("&".join(workflow_query))

        # Track all linked libraries (orcabus_id, library_id)
        linked_library_ids = {(orcabus_id, library_id)}

        for workflow_run in workflow_runs:
            wfr_orcabus_id = workflow_run["orcabus_id"]
            wfr_entity, _ = ExternalEntity.objects.get_or_create(
                orcabus_id=wfr_orcabus_id,
                defaults={
                    "prefix": workflow_run["prefix"],
                    "type": workflow_run["type"],
                    "service_name": workflow_run["service_name"],
                    "alias": workflow_run["alias"]
                }
            )
            CaseExternalEntityLink.objects.get_or_create(case=case, external_entity=wfr_entity)

            # Get libraries linked to this workflow run
            wfr_detail = get_workflow_run_detail(wfr_orcabus_id)
            for linked_lib in wfr_detail.get("libraries", []):
                linked_orcabus_id = linked_lib.get("orcabusId")
                linked_library_id = linked_lib.get("libraryId")
                if linked_orcabus_id and linked_library_id:
                    linked_library_ids.add((linked_orcabus_id, linked_library_id))

        # Link all discovered libraries to the case
        for linked_orcabus_id, linked_library_id in linked_library_ids:
            lib_entity, _ = ExternalEntity.objects.get_or_create(
                orcabus_id=linked_orcabus_id,
                defaults={
                    "prefix": "lib",
                    "type": "library",
                    "service_name": "metadata",
                    "alias": linked_library_id
                }
            )
            CaseExternalEntityLink.objects.get_or_create(case=case, external_entity=lib_entity)
