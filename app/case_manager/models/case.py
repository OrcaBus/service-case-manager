from django.db import models

from case_manager.fields import OrcaBusIdField
from case_manager.models.base import OrcaBusBaseModel, OrcaBusBaseManager


class CaseManager(OrcaBusBaseManager):
    pass


class Case(OrcaBusBaseModel):

    orcabus_id = OrcaBusIdField(primary_key=True, prefix='cas')  # TODO: allow more than 3 char for prefix?
    case_name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=255, null=True, blank=True)  # accreditation, clinical, research, ...?

    objects = CaseManager()

    def __str__(self):
        return f"ID: {self.orcabus_id}, case_name: {self.case_name}"

    def get_all_states(self):
        # retrieve all states (DB records rather than a queryset), using "related_name" definition on CaseState
        # TODO: ensure order by timestamp ?
        return list(self.states.all())

    def get_latest_state(self):
        # retrieve all related states and get the latest one
        return self.states.order_by('-timestamp').first()
