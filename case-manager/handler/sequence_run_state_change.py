import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from app.service.sequencing_state_update import update_sequencing_state_for_sequence_run

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    Lambda handler that processes an EventBridge SequenceRunStateChange event.

    This handler is only invoked for sequence runs with a "succeeded" status.

    Flow:
    1. Extract the sequence run ID from the event.
    2. Delegate to update_sequencing_state_for_sequence_run() which:
       a. Finds cases linked to the sequence run.
       b. Skips cases that are locked, completed, archived, or have no open
          sequencing round.
       c. Checks if all sequence runs for the case's libraries have succeeded.
       d. If yes, transitions the case state to "sequencing_completed".

    Duplicate links and already-transitioned cases are skipped without error.
    """
    logger.info(f"Processing SequenceRunStateChange event: {event}")

    detail = event.get("detail", {})
    sequence_run_orcabus_id = detail.get("id")

    if not sequence_run_orcabus_id:
        logger.warning("Skipping event: no 'id' found in detail.")
        return

    update_sequencing_state_for_sequence_run(sequence_run_orcabus_id)
