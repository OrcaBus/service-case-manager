from enum import Enum
import uuid
from datetime import datetime

import factory
from django.utils.timezone import make_aware

from case_manager.models.case import Case
from case_manager.models.case_state import CaseState
from case_manager.common.status import Status


class TestConstant():
    case_base_name = "TestCase-"
    library_1 = {
        "library_id": "L000001",
        "orcabus_id": "lib.01J5M2J44HFJ9424G7074NKTGN"
    }
    library_2 = {
        "library_id": "L000002",
        "orcabus_id": "lib.01J5M2J44HFJ9424G7074NKTGM"
    }


class CaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Case

    _uid = str(uuid.uuid4())
    case_name = f"{TestConstant.case_base_name}{_uid[:8]}"
    description = "Lorem ipsum..."
    type = "WGTS-clinical"


class CaseStateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CaseState

    status = Status.DRAFT.convention
    timestamp = make_aware(datetime.now())
    comment = "Comment"
    case = factory.SubFactory(CaseFactory)
