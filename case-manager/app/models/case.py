from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager
from app.models.comment import Comment
from app.models.state import State


class CaseManager(BaseManager):
    pass


class Case(BaseModel):
    objects = CaseManager()

    orcabus_id = OrcaBusIdField(primary_key=True, prefix='cas')
    title = models.CharField(
        unique=True,
        blank=True,
        null=True
    )
    description = models.CharField(
        blank=True,
        null=True
    )
    type = models.CharField(
        blank=True,
        null=True
    )
    last_modified = models.DateTimeField(auto_now=True)

    # Relationships
    user_set = models.ManyToManyField('User', through='CaseUserLink', related_name='case_set',
                                      blank=True)
    external_entity_set = models.ManyToManyField(
        'ExternalEntity',
        through='CaseExternalEntityLink',
        related_name='case_set',
        blank=True
    )


class CaseExternalEntityLink(models.Model):
    """
    This is just a many-many link between Case and ExternalEntity. Creating this model allows to override the 'db_column'
    field for foreign keys that makes it less confusion between the 'case_id' and 'orcabus_id' in the schema.
    """
    case = models.ForeignKey('Case', on_delete=models.CASCADE, db_column='case_orcabus_id')
    external_entity = models.ForeignKey('ExternalEntity', on_delete=models.CASCADE,
                                        db_column='external_entity_orcabus_id')

    added_via = models.CharField(
        blank=True,
        null=True,
        help_text="The external entity id that was added to the case"
    )
    timestamp = models.DateTimeField(auto_now=True)


class CaseUserLink(models.Model):
    """
    This is just a many-many link between Case and User. Creating this model allows to override the 'db_column'
    field for foreign keys that makes it less confusion between the 'case_id' and 'orcabus_id' in the schema.
    """
    case = models.ForeignKey('Case', on_delete=models.CASCADE, db_column='case_orcabus_id')
    user = models.ForeignKey('User', on_delete=models.CASCADE, db_column='user_orcabus_id')

    description = models.CharField(
        blank=True,
        null=True,
        help_text="Some description of the user in the case (e.g. 'Case Owner', 'Case Manager', etc.)"
    )
    timestamp = models.DateTimeField(auto_now=True)
