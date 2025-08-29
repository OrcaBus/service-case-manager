import logging

from unittest.mock import patch

from django.core import serializers
from django.test import TestCase
from .factories import USER_001, CASE_TITLE_001
from .factories import UserFactory, StateFactory, CaseFactory, ExternalEntityFactory
from .utils import insert_fixture_1
from ..models import CaseUserLink

# from .utils import insert_mock_1

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ModelTestCase(TestCase):
    def setUp(self):
        pass

    def test_create_user(self):
        """
        python manage.py test app.tests.test_models.ModelTestCase.test_create_user
        """

        case = insert_fixture_1()

        print(case.orcabus_id)
        print(case.description)
        print(case.external_entity_set.all())
        print(case.user_set.all())

    def test_get_simple_model(self):
        """
        python manage.py test app.tests.test_models.ModelTestCase.test_get_simple_model
        """

        logger.info("Test get on simple models")

        case = insert_fixture_1()
        self.assertEqual(case.title, CASE_TITLE_001, "correct user title assigned")

        # user
        self.assertEqual(
            case.user_set.all().count(), 1, "correct number of user linked to case"
        )
        user = case.user_set.get(name=USER_001)
        self.assertEqual(user.name, USER_001, "correct user name assigned")
        case_user_link = CaseUserLink.objects.get(case=case, user=user)
        self.assertEqual(
            case_user_link.description,
            "lead",
            "correct case user link description assigned",
        )

        # external entity
        self.assertEqual(
            case.external_entity_set.all().count(),
            2,
            "correct number of external entity linked to case",
        )
        external_entity_one = case.external_entity_set.get(alias="library-001")
        self.assertEqual(
            external_entity_one.alias,
            "library-001",
            "correct external entity alias assigned",
        )
        external_entity_two = case.external_entity_set.get(alias="library-002")
        self.assertEqual(
            external_entity_two.alias,
            "library-002",
            "correct external entity alias assigned",
        )

        # state
        states = case.state_set.all()
        self.assertEqual(states.count(), 2, "correct number of state linked to case")

        # comment
        comments = case.comment_set.all()
        self.assertEqual(
            comments.count(), 1, "correct number of comment linked to case"
        )
