from django.core.exceptions import ValidationError
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

    # Relationships
    case = models.ForeignKey(
        "Case",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        db_column="case_orcabus_id",
    )
    state = models.ForeignKey(
        "State",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        db_column="state_orcabus_id",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        db_column="created_by_user_orcabus_id",
        related_name="created_comments",
    )

    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        db_column="archived_by_user_orcabus_id",
        related_name="archived_comments",
    )

    def clean(self):
        # self.full_clean()
        super().clean()

        # Must be attached to at least a case or a state
        if not self.case and not self.state:
            raise ValidationError(
                "A comment must be associated with at least a 'case' or a 'state'."
            )

        # If both are set, they must refer to the same case
        if self.case and self.state:
            if self.state.case != self.case:
                raise ValidationError(
                    "comment.case and comment.state.case must refer to the same Case."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
