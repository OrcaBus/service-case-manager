from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class CaseStatus(models.TextChoices):
    # Intake
    REQUEST_RECEIVED = "request_received", "Request Received"
    SAMPLE_RECEIVED = "sample_received", "Sample Received"

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

    orcabus_id = OrcaBusIdField(primary_key=True)
    status = models.CharField(
        choices=CaseStatus.choices,
        blank=False,
        null=False,
        help_text="The status of the case.",
    )
    event_at = models.DateTimeField(
        blank=False,
        null=False,
        default=timezone.now,
        help_text="When the event actually occurred. May differ from timestamp for retrospective entries.",
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
        db_column="archive_by_user_orcabus_id",
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

        # Check that no fields other than is_archived and archived_at have changed
        immutable_fields = ["status", "event_at", "case_id"]
        for field in immutable_fields:
            if getattr(original, field) != getattr(self, field):
                raise ValidationError(
                    f"State records are immutable. Field '{field}' cannot be updated."
                )

        # Ensure is_archived actually changed (no-op updates not allowed)
        if original.is_archived == self.is_archived:
            raise ValidationError("State records are immutable and cannot be updated.")

        super().save(*args, **kwargs)
