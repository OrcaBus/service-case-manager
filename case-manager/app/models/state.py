from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class StateManager(BaseManager):
    pass


class State(BaseModel):
    objects = StateManager()

    orcabus_id = OrcaBusIdField(primary_key=True)
    status = models.CharField(
        blank=False,
        null=False,
        help_text="The status of the case."
    )

    timestamp = models.DateTimeField(auto_now=True)

    # Relationships
    case = models.ForeignKey('Case', on_delete=models.CASCADE, blank=False, null=False,
                             db_column='case_orcabus_id')