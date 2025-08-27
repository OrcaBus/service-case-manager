from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class CommentManager(BaseManager):
    pass


class Comment(BaseModel):
    objects = CommentManager()

    orcabus_id = OrcaBusIdField(primary_key=True)
    text = models.CharField(
        blank=True,
        null=True,
    )

    timestamp = models.DateTimeField(auto_now=True)

    # Relationships
    case = models.ForeignKey('Case', on_delete=models.CASCADE, blank=False, null=False,
                             db_column='case_orcabus_id')
    user = models.ForeignKey('User', on_delete=models.CASCADE, blank=False, null=False,
                             db_column='email')
    state = models.ForeignKey('State', on_delete=models.CASCADE, blank=True, null=True, db_column='state_orcabus_id')
