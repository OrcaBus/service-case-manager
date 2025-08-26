import factory
import factory.fuzzy
from factory.django import DjangoModelFactory
from app.models import User, State, Comment, ExternalEntity, Case

CASE_TITLES = ["case-001", "case-002", "case-003", "case-004", "case-005"]
CASE_TITLE_001 = "case-001"
CASE_TITLE_002 = "case-002"
USER_NAMES = ["Alice", "Bob", "John", "Eve", "Charlie"]
USER_001 = "Alice"
USER_OO2 = "Bob"
LIBRARY_001 = {
    "prefix": "lib",
    "orcabus_id": "01BX5ZZKBKACTAV9WEVGEMM001",
    "service_name": "metadata",
    "alias": "library-001"
}
LIBRARY_002 = {
    "prefix": "lib",
    "orcabus_id": "01BX5ZZKBKACTAV9WEVGEMM002",
    "service_name": "metadata",
    "alias": "library-002"
}
INDIVIDUAL_001 = {
    "prefix": "idv",
    "orcabus_id": "01BX5ZZKBKACTAV9WEVGEMM003",
    "service_name": "metadata",
    "alias": "individual-001"
}
SEQUENCE_RUN_001 = {
    "prefix": "seq",
    "orcabus_id": "01BX5ZZKBKACTAV9WEVGEMM004",
    "service_name": "sequence",
    "alias": "sequence-run-001"
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

    title = factory.Iterator(CASE_TITLES)
    description = "a description of the case"
    type = factory.fuzzy.FuzzyChoice(["WGTS", "CTTSO"])


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    name = factory.Iterator(USER_NAMES)
    email = factory.LazyAttribute(lambda o: f"{o.name.lower()}@umccr.org")


class StateFactory(DjangoModelFactory):
    class Meta:
        model = State

    status = factory.fuzzy.FuzzyChoice(['draft', 'pending', 'completed', 'archived'])


class CommentFactory(DjangoModelFactory):
    class Meta:
        model = Comment

    text = "some comment here"


class ExternalEntityFactory(DjangoModelFactory):
    class Meta:
        model = ExternalEntity
        exclude = ['test_data']

    test_data = factory.Iterator(EXTERNAL_ENTITIES)

    prefix = factory.LazyAttribute(lambda o: o.test_data["prefix"])
    orcabus_id = factory.LazyAttribute(lambda o: o.test_data["orcabus_id"])
    service_name = factory.LazyAttribute(lambda o: o.test_data["service_name"])
    alias = factory.LazyAttribute(lambda o: o.test_data["alias"])
