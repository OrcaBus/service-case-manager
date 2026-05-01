import factory
import factory.fuzzy
from factory.django import DjangoModelFactory
from app.models import User, State, Comment, ExternalEntity, Case
from app.models.case import CaseType, CaseStudyType
from app.models.state import CaseStatus

CASE_REQUEST_FORM_ID_001 = "case-001"
CASE_REQUEST_FORM_ID_002 = "case-002"
CASE_REQUEST_FORM_ID_ARRAY = ["case-001", "case-002", "case-003", "case-004", "case-005"]

USER_001 = "Alice"
USER_002 = "Bob"
USER_NAMES = ["Alice", "Bob", "John", "Eve", "Charlie"]

LIBRARY_001 = {
    "prefix": "lib",
    "service_name": "metadata",
    "alias": "library-001",
    "type": "library",
}
LIBRARY_002 = {
    "prefix": "lib",
    "service_name": "metadata",
    "alias": "library-002",
    "type": "library",
}
INDIVIDUAL_001 = {
    "prefix": "idv",
    "service_name": "metadata",
    "alias": "individual-001",
    "type": "individual",
}
SEQUENCE_RUN_001 = {
    "prefix": "seq",
    "service_name": "sequence",
    "alias": "sequence-run-001",
    "type": "sequence_run",
}
EXTERNAL_ENTITIES = [
    LIBRARY_001,
    LIBRARY_002,
    INDIVIDUAL_001,
    SEQUENCE_RUN_001,
]


class CaseFactory(DjangoModelFactory):
    class Meta:
        model = Case

    request_form_id = factory.Iterator(CASE_REQUEST_FORM_ID_ARRAY)
    description = "a description of the case"
    type = factory.fuzzy.FuzzyChoice(CaseType.values)
    study_type = factory.fuzzy.FuzzyChoice(CaseStudyType.values)
    is_report_required = True
    is_nata_accredited = True


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    name = factory.Iterator(USER_NAMES)
    email = factory.LazyAttribute(lambda o: f"{o.name.lower()}@umccr.org")


class StateFactory(DjangoModelFactory):
    class Meta:
        model = State

    status = factory.fuzzy.FuzzyChoice(CaseStatus.values)
    case = factory.SubFactory(CaseFactory)
    created_by = factory.SubFactory(UserFactory)


class CommentFactory(DjangoModelFactory):
    class Meta:
        model = Comment

    text = "some comment here"
    case = factory.SubFactory(CaseFactory)
    created_by = factory.SubFactory(UserFactory)


class ExternalEntityFactory(DjangoModelFactory):
    class Meta:
        model = ExternalEntity
        exclude = ["test_data"]

    test_data = factory.Iterator(EXTERNAL_ENTITIES)

    prefix = factory.LazyAttribute(lambda o: o.test_data["prefix"])
    service_name = factory.LazyAttribute(lambda o: o.test_data["service_name"])
    alias = factory.LazyAttribute(lambda o: o.test_data["alias"])
    type = factory.LazyAttribute(lambda o: o.test_data["type"])
