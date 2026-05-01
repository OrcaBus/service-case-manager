from django.core.exceptions import ObjectDoesNotExist
from django.core.management import call_command

from app.models import User, State, Comment, ExternalEntity, Case, CaseUserLink, CaseExternalEntityLink
from app.tests.factories import (
    UserFactory,
    StateFactory,
    CommentFactory,
    ExternalEntityFactory,
    CaseFactory,
    LIBRARY_001,
    LIBRARY_002,
    USER_001,
    CASE_REQUEST_FORM_ID_001,
)


def clear_all_data():
    """This function clear all existing models object"""
    call_command("flush", "--no-input")


def insert_fixture_1(clean_before_insert=True):
    """
    This function is a shortcut to clear and insert a set of mock data
    """
    if clean_before_insert:
        clear_all_data()

    case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
    user = UserFactory(name=USER_001)

    state_received = StateFactory(case=case, status="request_received", created_by=user)
    state_started = StateFactory(
        case=case, status="sequencing_started", created_by=user
    )

    comment = CommentFactory(case=case, created_by=user)

    lib_1 = ExternalEntityFactory(**LIBRARY_001)
    CaseExternalEntityLink.objects.create(case=case, external_entity=lib_1)

    lib_2 = ExternalEntityFactory(**LIBRARY_002)
    CaseExternalEntityLink.objects.create(case=case, external_entity=lib_2)

    # Linking
    CaseUserLink.objects.create(case=case, user=user, description="lead")

    return case


def is_obj_exists(obj, **kwargs):
    try:
        obj.objects.get(**kwargs)
        return True
    except ObjectDoesNotExist:
        return False
