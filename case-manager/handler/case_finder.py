import os
import logging
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from app.service.case_finder import cttso_case_builder, wgts_case_builder

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context) -> dict[str, str]:

    try:
        cttso_case_builder()
        wgts_case_builder()

        logger.info("Case builder succeeded.")
        return {"Status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Case creation failed: {e}", exc_info=True)
        raise e
