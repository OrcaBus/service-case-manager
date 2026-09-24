import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from app.service.bioinfo_state_update import update_bioinfo_state_for_workflow_run

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    Lambda handler that processes an EventBridge WorkflowRunStateChange event.

    Flow:
    1. Extract the workflow run orcabus id from the event detail.
    2. Delegate to update_bioinfo_state_for_workflow_run() which:
       a. Finds cases linked to the workflow run.
       b. Skips cases that are locked, completed, or archived.
       c. Checks the workflow API for every workflow run linked to the case:
          - If any run is still ongoing  -> transitions to "bioinformatics_started".
          - If none is ongoing (all done) -> transitions to "bioinformatics_completed".
       d. Skips the transition if the case is already in the target status.
    """
    logger.info(f"Processing WorkflowRunStateChange event: {event}")

    detail = event.get("detail", {})
    workflow_run_orcabus_id = detail.get("orcabusId")

    if not workflow_run_orcabus_id:
        logger.warning("Skipping event: no 'orcabusId' found in detail.")
        return

    update_bioinfo_state_for_workflow_run(workflow_run_orcabus_id)
