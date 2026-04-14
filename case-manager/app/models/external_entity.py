from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class ExternalEntityManager(BaseManager):
    pass


class ExternalEntity(BaseModel):
    objects = ExternalEntityManager()

    orcabus_id = OrcaBusIdField(primary_key=True)
    prefix = models.CharField(
        blank=True,
        null=True,
        help_text="The prefix in the orcabus_id, indicating the entity's type or source system. Used to distinguish "
                  "between different entity types or services.",
    )

    type = models.CharField(
        blank=True,
        null=True,
        help_text="The entity type within its service, e.g., 'library', 'subject', or 'sequence'. Typically matches "
                  "the subpath or resource type in the source service.",
    )

    service_name = models.CharField(
        blank=True,
        null=True,
        help_text="The name of the microservice or domain where the entity is managed, e.g., 'metadata', 'workflow', "
                  "or 'sequence'.",
    )
    alias = models.CharField(
        blank=True,
        null=True,
        help_text="A human-friendly identifier for this entity, such as a library ID or workflow run ID, for easier "
                  "recognition than the orcabus_id.",
    )
