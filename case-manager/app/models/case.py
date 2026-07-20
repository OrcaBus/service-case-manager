from django.core.validators import URLValidator
from django.db import models
from rest_framework.exceptions import ValidationError

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager, BaseHistoricalRecords
from app.models.state import CaseStatus


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
    timestamp = models.DateTimeField(auto_now_add=True)

    # history
    history = BaseHistoricalRecords()

    class Meta:
        unique_together = ["case", "user"]


class CaseExternalEntityLink(models.Model):
    """
    Many-to-many link between Case and ExternalEntity.

    Linking is **blocked** when the case's current status is one of
    ``BLOCKED_LINK_STATUSES`` (locked, completed, or archived).  These statuses
    signal that the case is either under review or fully closed; attaching new
    external entities at that point would silently corrupt the audit trail.

    To allow linking again, the case must be transitioned out of the blocked
    state (e.g. unlocked → back to an active status).  This guard is enforced at
    the model level so that *all* code paths — API viewsets, Lambda handlers, and
    management commands — respect the same rule.
    """

    # Statuses that prevent new external-entity links from being created.
    # To re-allow linking, the case must be transitioned out of one of these states.
    BLOCKED_LINK_STATUSES = frozenset(
        {CaseStatus.LOCKED, CaseStatus.COMPLETED, CaseStatus.ARCHIVED}
    )

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

    def _assert_case_not_blocked(self) -> None:
        """Raise ValidationError if the case is in a state that blocks link modifications."""
        from app.models.state import State

        current_state = (
            State.objects.filter(case=self.case, is_archived=False)
            .order_by("-created_at")
            .first()
        )
        if current_state and current_state.status in self.BLOCKED_LINK_STATUSES:
            raise ValidationError(
                f"Cannot modify an external entity link on case '{self.case_id}': "
                f"the case is currently '{current_state.status}'. "
                f"Transition the case out of this state before modifying links."
            )

    def save(self, *args, **kwargs):
        self._assert_case_not_blocked()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._assert_case_not_blocked()
        super().delete(*args, **kwargs)


class Case(BaseModel):
    objects = CaseManager()
    orcabus_id = OrcaBusIdField(primary_key=True, prefix="cas")

    # ------------------------------------------------------------------
    # REDCap-managed fields
    #
    # Populated EXCLUSIVELY by the REDCap import service
    # (app/service/redcap_import.py), which writes directly via the ORM
    # and never goes through the REST API. These fields MUST NOT be
    # writable through the public REST API.
    #
    # If this set grows significantly, consider extracting these into a
    # dedicated CaseRedcapData(OneToOne→Case) model to make ownership
    # boundaries explicit at the schema level.
    # ------------------------------------------------------------------
    REDCAP_MANAGED_FIELDS = (
        "request_form_id",
        "type",
        "study_name",
        "study_id",
        "ur_number"
    )

    request_form_id = models.CharField(
        unique=True,
        blank=False,
        null=False,
        help_text="[REDCap-managed] The unique ID from REDCap ('request_id') associated with this case.",
    )
    type = models.CharField(
        choices=CaseType.choices,
        blank=False,
        null=False,
        help_text="[REDCap-managed] The type for this case, mapped from REDCap 'rf_test_requested'. "
                  f"One of: {', '.join(c[0] for c in CaseType.choices)}",
    )
    study_name = models.CharField(
        blank=True,
        null=True,
        help_text="[REDCap-managed] The study_name for this case as recorded in REDCap.",
    )
    study_id = models.CharField(
        blank=True,
        null=True,
        help_text="[REDCap-managed] The study_id within the defined study_name as recorded in REDCap.",
    )
    ur_number = models.CharField(
        blank=True,
        null=True,
        help_text="[REDCap-managed] The UR (Unit Record) number for this case, as recorded in REDCap.",
    )

    # ------------------------------------------------------------------
    # API-editable fields
    # Freely writable through the public REST API. No REDCap involvement.
    # ------------------------------------------------------------------
    description = models.CharField(
        blank=True, null=True, help_text="A brief description of the case"
    )
    study_type = models.CharField(
        choices=CaseStudyType.choices,
        blank=False,
        null=False,
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
    links = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        validators=[validate_urls_dict],
        help_text='A dict of named links, e.g. {"trello": "https://...", "drive": "https://..."}',
    )
    alias = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="A list of aliases for this case, typically populated with external IDs to make searching easier.",
    )
    due_date = models.DateField(
        blank=True,
        null=True,
        help_text="The due date for the report.",
    )

    # Links to other models
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
