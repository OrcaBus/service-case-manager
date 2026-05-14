import os
import logging
import django
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.base")
django.setup()

from app.service.redcap_import import (
    upsert_redcap_records_by_date_range,
    auto_sync_redcap_records,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, _context):
    result = auto_sync_redcap_records()

    logger.info(
        f"Processing REDCap records completed: {result['synced']} synced, {result['failed']} failed"
    )
