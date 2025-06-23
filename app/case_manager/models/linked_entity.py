from django.db import models

from case_manager.fields import OrcaBusIdField
from case_manager.models.case import Case
from case_manager.models.base import OrcaBusBaseModel, OrcaBusBaseManager


class LinkedEntityManager(OrcaBusBaseManager):
    pass


class LinkedEntity(OrcaBusBaseModel):
    # TODO: find better name? (CaseEntity? CaseLink? CaseReference? CaseMeta? CaseMetadata?...)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['case', 'entity_orcabus_id'],
                name='unique_case_entity_id'
            )
        ]

    case = models.ForeignKey(Case, on_delete=models.CASCADE)
    entity_orcabus_id = OrcaBusIdField(prefix='ref')  # TODO: document that this prefix is NOT the original one, it only indicates that the OID is a REFerence to an existing entity
    entity_name = models.CharField(max_length=255, null=True, blank=True)
    entity_type = models.CharField(max_length=255)

    objects = LinkedEntityManager()

    def __str__(self):
        return f"Entity id: {self.entity_orcabus_id}, case id: {self.case}, type: {self.entity_type}, ref name: {self.entity_name}"
