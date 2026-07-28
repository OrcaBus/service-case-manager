from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class CaseStatus(models.TextChoices):
    # Intake
    REQUEST_RECEIVED = "request_received", "Request Received"
    WGTS_TUMOUR_SAMPLE_RECEIVED = (
        "wgts_tumour_sample_received",
        "WGTS Tumour Sample Received",
    )
    WGTS_GERMLINE_SAMPLE_RECEIVED = (
        "wgts_germline_sample_received",
        "WGTS Germline Sample Received",
    )
    CTTSO_SAMPLE_RECEIVED = "cttso_sample_received", "CTTSO Sample Received"
    ALL_SAMPLE_RECEIVED = "all_sample_received", "All Sample Received"

    # Library preparation
    LIBRARY_PARTIALLY_FAILED = "library_partially_failed", "Library Partially Failed"

    # Sequencing
    SEQUENCING_STARTED = "sequencing_started", "Sequencing Started"
    SEQUENCING_COMPLETED = "sequencing_completed", "Sequencing Completed"

    # Bioinformatics Analysis and Workflows
    BIOINFORMATICS_STARTED = "bioinformatics_started", "Bioinformatics Started"
    BIOINFORMATICS_COMPLETED = "bioinformatics_completed", "Bioinformatics Completed"

    # Curation
    CURATION_STARTED = "curation_started", "Curation Started"
    CURATION_COMPLETED = "curation_completed", "Curation Completed"

    # Reporting
    LOCKED = "locked", "Locked"
    UNLOCKED = "unlocked", "Unlocked"

    # Terminal
    FAILED = "failed", "Failed"
    COMPLETED = "completed", "Completed"
    ARCHIVED = "archived", "Archived"


class StateManager(BaseManager):
    pass


class State(BaseModel):
    objects = StateManager()

    # ------------------------------------------------------------------
    # Default deny: any concrete field NOT listed in API_WRITABLE_FIELDS
    # is read-only via the public REST API (see get_read_only_fields()).
    # `is_archived` is intentionally excluded — it has its own dedicated
    # archive endpoint and is never set through the regular serializer.
    # ------------------------------------------------------------------
    API_WRITABLE_FIELDS = ("status", "event_date", "event_time", "case")

    @classmethod
    def get_read_only_fields(cls) -> tuple:
        """All concrete fields not in API_WRITABLE_FIELDS (e.g. audit fields, pk)."""
        return tuple(
            f.name
            for f in cls._meta.fields
            if f.name not in cls.API_WRITABLE_FIELDS and f.name != "orcabus_id"
        )

    orcabus_id = OrcaBusIdField(primary_key=True)
    status = models.CharField(
        choices=CaseStatus.choices,
        blank=False,
        null=False,
        help_text="The status of the case.",
    )
    event_date = models.DateField(
        blank=False,
        null=False,
        default=timezone.now,
        help_text="When the event actually occurred. May differ from created_at for retrospective entries.",
    )
    event_time = models.TimeField(
        blank=True,
        null=True,
        help_text="When the event time actually occurred. May differ from created_at for retrospective entries.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        db_column="created_by_user_orcabus_id",
        related_name="created_states",
    )
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="archived_by_user_orcabus_id",
        related_name="archived_states",
    )
    # Relationships
    case = models.ForeignKey(
        "Case",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
        db_column="case_orcabus_id",
    )

    def delete(self, *args, **kwargs):
        raise ValueError("State records are immutable and cannot be deleted.")

    def save(self, *args, **kwargs):
        # Allow creation freely
        if not State.objects.filter(pk=self.pk).exists():
            super().save(*args, **kwargs)
            return

        # Only allow archiving an existing state
        original = State.objects.get(pk=self.pk)

        mutable_fields = {"is_archived", "archived_at", "archived_by_id"}
        for field in self._meta.fields:
            if field.attname in mutable_fields:
                continue
            if getattr(original, field.attname) != getattr(self, field.attname):
                raise ValidationError(
                    f"State records are immutable. Field '{field.attname}' cannot be updated."
                )

        # Ensure is_archived actually changed (no-op updates not allowed)
        if original.is_archived == self.is_archived:
            raise ValidationError("State records are immutable and cannot be updated.")

        super().save(*args, **kwargs)
