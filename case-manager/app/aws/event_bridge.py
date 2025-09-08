import boto3
import logging
import os
from typing import Dict, Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)  # Use __name__ for better logger naming
logger.setLevel(logging.INFO)

SOURCE = "orcabus.casemanager"
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME")
EVENT_BUS_ENABLED = os.environ.get("EVENT_BUS_ENABLED", "true").lower() == "true"

# Initialize AWS client
client = boto3.client("events", region_name="ap-southeast-2")


def emit_event(detail_type: str, event_detail_model: BaseModel) -> Dict[str, Any]:
    """
    Emit an event to AWS EventBridge.

    Args:
        detail_type: The type of the event (e.g., "CaseEntityRelationshipChange")
        event_detail_model: Pydantic model containing the event details

    Returns:
        The response from AWS EventBridge API

    Raises:
        ValueError: If EVENT_BUS_NAME is not set
        ClientError: If AWS EventBridge API call fails
    """

    if not EVENT_BUS_ENABLED:
        logger.warning("Event bus is disabled. Skipping event emission.")
        return {}

    if not EVENT_BUS_NAME:
        raise ValueError("EVENT_BUS_NAME environment variable is not set")

    # Serialize the Pydantic model to JSON
    event_detail_json = event_detail_model.model_dump_json()

    try:
        response = client.put_events(
            Entries=[
                {
                    "Source": SOURCE,
                    "DetailType": detail_type,
                    "Detail": event_detail_json,
                    "EventBusName": EVENT_BUS_NAME,
                },
            ],
        )

        # Log success with prettified JSON
        logger.info(f"Sent {detail_type} event to event bus: {EVENT_BUS_NAME}")
        logger.info(event_detail_model.model_dump_json())

        return response
    except Exception as e:
        logger.error(f"Failed to emit event {detail_type}: {str(e)}")
        raise
