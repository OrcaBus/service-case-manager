import os
import logging
import django
from datetime import datetime, timedelta

from app.service.redcap_import import upsert_redcap_records_by_date_range

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, _context):
    event_source = event.get("source")
    if event_source == "aws.events":
        # If this is triggered from
        today = datetime.now().date()
        seven_days_ago = (today - timedelta(days=7)).isoformat()
        logger.info(f"Processing REDCap records from {seven_days_ago}")
        result = upsert_redcap_records_by_date_range(after_date=seven_days_ago)
    else:
        # expect after_date and/or before_date is given on the event
        after_date = event.get("after_date", None)
        before_date = event.get("before_date", None)

        if after_date is None:
            raise RuntimeError("after_date is required")
        logger.info(f"Processing REDCap records with after_date={after_date} and before_date={before_date}")
        result = upsert_redcap_records_by_date_range(after_date=after_date, before_date=before_date)

    logger.info(f"Processing REDCap records completed: {result['synced']} synced, {result['failed']} failed")
