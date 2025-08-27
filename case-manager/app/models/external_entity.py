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
        help_text="The prefix used in the orcabus_id. Each orcabus_id has a prefix that may correspond to the same or different service names. This indicates which entity the ID belongs to."
    )

    type = models.CharField(
        blank=True,
        null=True,
        help_text="The entity type within its service, local to that service. Typically, this matches the subpath to the entity, such as library, subject, or sequence."
    )

    service_name = models.CharField(
        blank=True,
        null=True,
        help_text="The domain name or microservice name where the actual entity is stored. E.g. metadata, workflow, sequence"
    )
    alias = models.CharField(
        blank=True,
        null=True,
        help_text="A human-readable name or alias for this entity, such as a library ID or workflow run ID, for easier identification than the orcabus_id.",
    )
