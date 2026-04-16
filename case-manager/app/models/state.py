from django.db import models

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
        blank=False, null=False, help_text="The status of the case."
    )

    timestamp = models.DateTimeField(auto_now=True)

    # Relationships
    case = models.ForeignKey(
        "Case",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
        db_column="case_orcabus_id",
    )
