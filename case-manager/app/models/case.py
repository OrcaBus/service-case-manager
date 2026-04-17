from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager, BaseHistoricalRecords


class CaseStudyType(models.TextChoices):
    CLINICAL = "clinical", "Clinical"
    RESEARCH = "research", "Research"


class CaseType(models.TextChoices):
    WGTS = "wgts", "WGTS"
    CTTSO = "cttso", "ctTSO"


class CaseManager(BaseManager):
    pass


class CaseUserLink(models.Model):
    """
    This is just a many-many link between Case and User. Creating this model allows to override the 'db_column'
    field for foreign keys that makes it less confusion between the 'case_id' and 'orcabus_id' in the schema.
    """

    case = models.ForeignKey(
        "Case", on_delete=models.CASCADE, db_column="case_orcabus_id"
    )
    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, db_column="user_orcabus_id"
    )

    description = models.CharField(
        blank=True,
        null=True,
        help_text="Some description of the user in the case (e.g. 'Case Owner', 'Case Manager', etc.)",
    )
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["case", "user"]


class CaseExternalEntityLink(models.Model):
    """
    This is just a many-many link between Case and ExternalEntity. Creating this model allows to override the 'db_column'
    field for foreign keys that makes it less confusion between the 'case_id' and 'orcabus_id' in the schema.
    """

    case = models.ForeignKey(
        "Case", on_delete=models.CASCADE, db_column="case_orcabus_id"
    )
    external_entity = models.ForeignKey(
        "ExternalEntity",
        on_delete=models.CASCADE,
        db_column="external_entity_orcabus_id",
    )

    added_via = models.CharField(
        blank=True,
        null=True,
        help_text="The external entity id that was added to the case",
    )
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["case", "external_entity"]


class Case(BaseModel):
    objects = CaseManager()

    orcabus_id = OrcaBusIdField(primary_key=True, prefix="cas")
    title = models.CharField(unique=True, blank=True, null=True)
    description = models.CharField(blank=True, null=True, help_text="A brief description of the case")
    type = models.CharField(
        choices=CaseType.choices, blank=False, null=True,
        help_text="The type for this case e.g. WGTS, ctTSO",
    )
    study_type = models.CharField(
        choices=CaseStudyType.choices, blank=False, null=True,
        help_text="""Whether this is a "clinical" or "research" case""",
    )
    is_report_required = models.BooleanField(
        default=True,
        help_text="Whether a report is required for this case",
    )
    is_nata_accredited = models.BooleanField(
        default=True,
        help_text="Whether a case is a NATA accredited case",
    )
    trello_url = models.URLField(blank=True, null=True, help_text="The URL to the Trello board")
    alias = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="A list of aliases for this case, typically populated with external IDs to make searching easier.",
    )
    last_modified = models.DateTimeField(auto_now=True)

    user_set = models.ManyToManyField(
        "User", through=CaseUserLink, related_name="case_set", blank=True
    )
    external_entity_set = models.ManyToManyField(
        "ExternalEntity",
        through=CaseExternalEntityLink,
        related_name="case_set",
        blank=True,
    )

    # history
    history = BaseHistoricalRecords(m2m_fields=[user_set, external_entity_set])
