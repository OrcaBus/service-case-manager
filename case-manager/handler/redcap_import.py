import os
import logging
import django
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from app.service.redcap_import import upsert_redcap_records_by_date_range

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, _context):
    event_source = event.get("source")

    if event_source == "aws.events":
        # Triggered on a schedule — sync records for today
        after_date = datetime.now().date().isoformat()
        before_date = None
    else:
        # Manual invocation — after_date is required, before_date is optional
        after_date = event.get("after_date")
        before_date = event.get("before_date")

        if not after_date:
            raise RuntimeError("after_date is required")

    logger.info(
        f"Processing REDCap records with after_date={after_date}"
        + (f" and before_date={before_date}" if before_date else "")
    )

    result = upsert_redcap_records_by_date_range(
        after_date=after_date, before_date=before_date
    )

    logger.info(
        f"Processing REDCap records completed: {result['synced']} synced, {result['failed']} failed"
    )
