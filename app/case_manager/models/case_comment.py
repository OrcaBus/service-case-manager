from django.db import models

from case_manager.fields import OrcaBusIdField
from case_manager.models.base import OrcaBusBaseModel, OrcaBusBaseManager
from case_manager.models.case import Case


class CaseCommentManager(OrcaBusBaseManager):
    pass


class CaseComment(OrcaBusBaseModel):

    orcabus_id = OrcaBusIdField(primary_key=True, prefix='cco')  # TODO: allow more than 3 char for prefix?
    case = models.ForeignKey(Case, related_name="comments", on_delete=models.CASCADE)
    comment = models.TextField()
    created_by = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    objects = CaseCommentManager()

    def __str__(self):
        return f"ID: {self.orcabus_id}, case: {self.case}, comment: {self.comment}"
