from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseManager


class PendingExternalEntityManager(BaseManager):
    pass


class PendingExternalEntity(models.Model):
    """
    Transient queue record for an external entity alias sourced from the case's REDCap payload,
    waiting for the originating microservice to assign its orcabus_id.

    Once the microservice creates the entity and its orcabus_id is known, a CaseExternalEntityLink
    is created and this record is deleted.
    """

    objects = PendingExternalEntityManager()

    orcabus_id = OrcaBusIdField(
        primary_key=True,
        help_text="Internal record ID for this pending entity entry.",
    )
    case = models.ForeignKey(
        "Case",
        on_delete=models.CASCADE,
        related_name="pending_external_entities",
        db_column="case_orcabus_id",
        help_text="The case this pending external entity is associated with.",
    )
    alias = models.CharField(
        blank=True,
        null=True,
        help_text=(
            "Human-readable identifier sourced from the REDCap payload that is expected to map "
            "one-to-one with the orcabus_id once the entity is created by the originating microservice "
            "(e.g. a library ID such as 'LIB_001'). Corresponds to ExternalEntity.alias after resolution."
        ),
    )
    type = models.CharField(
        blank=True,
        null=True,
        help_text=(
            "The entity type within its originating service, e.g., 'library', 'sample', or 'workflowrun'. "
            "Typically matches the resource type or subpath in the source service API."
        ),
    )
    service_name = models.CharField(
        blank=True,
        null=True,
        help_text=(
            "The name of the microservice or domain expected to create this entity, "
            "e.g., 'metadata', 'workflow', or 'sequence'."
        ),
    )

    class Meta:
        unique_together = ("alias", "type", "service_name")
