from django.core.exceptions import ObjectDoesNotExist

from app.models import User, State, Comment, ExternalEntity, Case, CaseUserLink
from app.tests.factories import (
    UserFactory,
    StateFactory,
    CommentFactory,
    ExternalEntityFactory,
    CaseFactory,
    LIBRARY_001,
    LIBRARY_002,
    USER_001,
    CASE_TITLE_001,
)


def clear_all_data():
    """This function clear all existing models object"""
    User.objects.all().delete()
    State.objects.all().delete()
    Comment.objects.all().delete()
    ExternalEntity.objects.all().delete()
    Case.objects.all().delete()


def insert_fixture_1(clean_before_insert=True):
    """
    This function is a shortcut to clear and insert a set of mock data
    """
    if clean_before_insert:
        clear_all_data()

    case = CaseFactory(title=CASE_TITLE_001)
    user = UserFactory(name=USER_001)

    state_draft = StateFactory(case=case, status="draft")
    state_pending = StateFactory(case=case, status="pending")

    comment = CommentFactory(case=case, user=user)
    lib_1 = ExternalEntityFactory(**LIBRARY_001)
    case.external_entity_set.add(lib_1, through_defaults={"added_via": "import"})

    lib_2 = ExternalEntityFactory(**LIBRARY_002)
    case.external_entity_set.add(lib_2, through_defaults={"added_via": "manual"})

    # Linking
    case.user_set.add(user, through_defaults={"description": "lead"})

    return case


def is_obj_exists(obj, **kwargs):
    try:
        obj.objects.get(**kwargs)
        return True
    except ObjectDoesNotExist:
        return False
