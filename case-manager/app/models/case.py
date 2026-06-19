from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager, BaseHistoricalRecords


def validate_urls_dict(value):
    """Validates that the value is a dict of {label: valid_url} pairs."""
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValidationError(
            "urls must be a JSON object (dict), e.g. {'trello': 'https://...'}"
        )
    url_validator = URLValidator()
    errors = {}
    for key, url in value.items():
        if not isinstance(key, str) or not key.strip():
            errors[key] = "Each key must be a non-empty string."
            continue
        try:
            url_validator(url)
        except ValidationError:
            errors[key] = f"'{url}' is not a valid URL."
    if errors:
        raise ValidationError(errors)


class CaseStudyType(models.TextChoices):
    CLINICAL = "clinical", "Clinical"
    RESEARCH = "research", "Research"


class CaseType(models.TextChoices):
    WGTS = "wgts", "WGTS_T-N"
    CTTSO = "cttso", "ctTSO500"
    WGS_N = "wgs_n", "WGS_N"


class CaseManager(BaseManager):
    pass


class CaseUserLink(models.Model):
    """
    Explicit many-to-many link between a Case and a User.
    Defined as a through-model to allow overriding db_column names, avoiding ambiguity
    between case_id and orcabus_id in the schema, and to capture per-link metadata (description, timestamp).
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
    timestamp = models.DateTimeField(auto_now_add=True)

    # history
    history = BaseHistoricalRecords()

    class Meta:
        unique_together = ["case", "user"]


class CaseExternalEntityLink(models.Model):
    """
    Confirmed many-to-many link between a Case and a fully-resolved ExternalEntity.
    Uses explicit db_column names to avoid ambiguity between case_id and orcabus_id in the schema.
    Only created once the ExternalEntity orcabus_id has been assigned by the originating microservice.
    """

    case = models.ForeignKey(
        "Case", on_delete=models.CASCADE, db_column="case_orcabus_id"
    )
    external_entity = models.ForeignKey(
        "ExternalEntity",
        on_delete=models.CASCADE,
        db_column="external_entity_orcabus_id",
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    # history
    history = BaseHistoricalRecords()

    class Meta:
        unique_together = ["case", "external_entity"]


class Case(BaseModel):
    objects = CaseManager()

    orcabus_id = OrcaBusIdField(primary_key=True, prefix="cas")
    request_form_id = models.CharField(
        unique=True,
        blank=False,
        null=False,
        help_text=(
            "Unique identifier from the external request form that originated this case. "
            "Used as the correlation key when linking external entities that arrive asynchronously."
        ),
    )
    description = models.CharField(
        blank=True,
        null=True,
        help_text="A brief human-readable description of the case.",
    )
    type = models.CharField(
        choices=CaseType.choices,
        blank=False,
        null=False,
        help_text=f"Workflow/assay type for this case. One of: {', '.join(c[0] for c in CaseType.choices)}",
    )
    study_type = models.CharField(
        choices=CaseStudyType.choices,
        blank=False,
        null=False,
        help_text='Whether this is a "clinical" or "research" case.',
    )
    is_report_required = models.BooleanField(
        default=True,
        help_text="Whether a formal report must be produced for this case.",
    )
    is_nata_accredited = models.BooleanField(
        default=True,
        help_text="Whether this case is processed under NATA accreditation.",
    )
    links = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        validators=[validate_urls_dict],
        help_text='Named external URLs related to this case, e.g. {"trello": "https://...", "drive": "https://..."}',
    )
    alias = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text=(
            "List of alternative identifiers for this case (e.g. external system IDs). "
            "Populated to make searching and cross-referencing easier."
        ),
    )
    redcap_payload = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        help_text=(
            "Snapshot of the latest raw REDCap payload received for this case. "
            "Not all REDCap fields are mapped to structured Django fields — this preserves the full "
            "source data for audit and UI rendering of REDCap information."
        ),
    )

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
    history = BaseHistoricalRecords()


@receiver(m2m_changed, sender=CaseUserLink)
def prevent_caseuserlink_m2m_add(sender, action, **kwargs):
    if action in ("pre_add", "pre_remove"):
        raise RuntimeError(
            "Do not use case.user_set.add() or case.user_set.remove(). "
            "Use CaseUserLink.objects.create(case=case, user=user) to add, "
            "and link.delete() to remove. "
            "Reason: .add()/.remove() bypass save() and history will NOT be recorded."
        )


@receiver(m2m_changed, sender=CaseExternalEntityLink)
def prevent_caseexternalentitylink_m2m_add(sender, action, **kwargs):
    if action in ("pre_add", "pre_remove"):
        raise RuntimeError(
            "Do not use case.external_entity_set.add() or case.external_entity_set.remove(). "
            "Use CaseExternalEntityLink.objects.create(case=case, external_entity=...) to add, "
            "and link.delete() to remove. "
            "Reason: .add()/.remove() bypass save() and history will NOT be recorded."
        )
