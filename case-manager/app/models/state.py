from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class CaseStatus(models.TextChoices):
    # Intake
    REQUEST_RECEIVED = "request_received", "Request Received"
    SAMPLE_RECEIVED = "sample_received", "Sample Received"

    # Library preparation
    LIBRARY_PREP_STARTED = "library_prep_started", "Library Preparation Started"
    LIBRARY_QC_FAILED = "library_qc_failed", "Library QC Failed"
    LIBRARY_QC_REQUEUE = "library_qc_requeue", "Library QC Re-queued"

    # Sequencing
    SEQUENCING_STARTED = "sequencing_started", "Sequencing Started"
    SEQUENCING_COMPLETE = "sequencing_complete", "Sequencing Complete"

    # Analysis
    ANALYSIS_STARTED = "analysis_started", "Analysis Started"
    ANALYSIS_COMPLETE = "analysis_complete", "Analysis Complete"

    # Curation
    READY_FOR_CURATION = "ready_for_curation", "Ready for Curation"
    CURATION_STARTED = "curation_started", "Curation Started"
    CURATION_COMPLETE = "curation_complete", "Curation Complete"

    # Reporting
    LOCKED_FOR_REPORTING = "locked_for_reporting", "Locked for Reporting"

    # Terminal
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
