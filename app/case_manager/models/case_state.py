from django.db import models

from case_manager.fields import OrcaBusIdField
from case_manager.models.base import OrcaBusBaseModel, OrcaBusBaseManager
from case_manager.models.case import Case
from case_manager.common.status import Status


class CaseStateManager(OrcaBusBaseManager):
    pass


class CaseState(OrcaBusBaseModel):
    class Meta:
        unique_together = ["case", "status", "timestamp"]

    # --- mandatory fields
    orcabus_id = OrcaBusIdField(primary_key=True, prefix='css')  # TODO: allow more than 3 char for prefix?
    status = models.CharField(max_length=255)
    timestamp = models.DateTimeField()
    comment = models.CharField(max_length=255, null=True, blank=True)

    case = models.ForeignKey(Case, related_name='states', on_delete=models.CASCADE)

    objects = CaseStateManager()

    def __str__(self):
        return f"ID: {self.orcabus_id}, status: {self.status}"

    def is_terminal(self) -> bool:
        return Status.is_terminal(str(self.status))

    def is_draft(self) -> bool:
        return Status.is_draft(str(self.status))

    def is_ready(self) -> bool:
        return Status.is_ready(str(self.status))

    def is_running(self) -> bool:
        return Status.is_running(str(self.status))
