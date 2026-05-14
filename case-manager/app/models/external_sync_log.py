from django.db import models


class ExternalService(models.TextChoices):
    REDCAP = "redcap", "REDCap"


class ExternalSyncLog(models.Model):
    """
    Tracks the last import timestamp from external data sources (e.g. REDCap).

    When syncing, the external service is queried over a date range — from the
    last recorded sync date up to the current trigger time. This allows
    incremental fetches rather than full reloads on every sync.
    """

    external_service = models.CharField(
        choices=ExternalService.choices,
        blank=False,
        null=False,
    )

    imported_at = models.DateTimeField(
        help_text="The timestamp of the last successful sync with the external service. This is used as the starting "
        "point for the next sync.",
        blank=False,
        null=False,
    )
