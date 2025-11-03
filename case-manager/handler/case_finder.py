import os
import json
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from app.service.case_finder import create_case_from_library_findings

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context) -> dict[str, str]:
    logger.info(f"Processing event: {json.dumps(event, indent=4)}")

    case_type = event.get("case_type", None)
    library_id_array = event.get("library_id_array", None)

    if not isinstance(library_id_array, list):
        logger.error("library_id_array must be a list.")
        raise ValueError("library_id_array must be a list.")

    try:
        create_case_from_library_findings(
            case_type=case_type, library_id_array=library_id_array
        )
        logger.info("Case creation succeeded.")
        return {"Status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Case creation failed: {e}", exc_info=True)
        raise e
