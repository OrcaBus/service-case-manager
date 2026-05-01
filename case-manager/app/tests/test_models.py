import logging

from django.core.exceptions import ValidationError
from django.test import TestCase
from .factories import USER_001, CASE_REQUEST_FORM_ID_001, CASE_REQUEST_FORM_ID_002
from .factories import UserFactory, StateFactory, CaseFactory, ExternalEntityFactory
from .utils import insert_fixture_1
from ..models import CaseUserLink, Comment

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
        self.assertEqual(case.request_form_id, CASE_REQUEST_FORM_ID_001, "correct request form id assigned")

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


class CommentModelTestCase(TestCase):
    """
    python manage.py test app.tests.test_models.CommentModelTestCase
    """

    def setUp(self):
        self.case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self.user = UserFactory(name=USER_001)
        self.state = StateFactory(
            case=self.case, status="request_received", created_by=self.user
        )

    # --- Valid creation ---

    def test_comment_with_case_only(self):
        """
        python manage.py test app.tests.test_models.CommentModelTestCase.test_comment_with_case_only
        A comment attached only to a case should be valid.
        """
        comment = Comment(text="Valid comment", case=self.case, created_by=self.user)
        comment.full_clean()  # should not raise
        comment.save()
        self.assertEqual(Comment.objects.count(), 1)

    def test_comment_with_state_only(self):
        """
        python manage.py test app.tests.test_models.CommentModelTestCase.test_comment_with_state_only
        A comment attached only to a state should be valid.
        """
        comment = Comment(text="Valid comment", state=self.state, created_by=self.user)
        comment.full_clean()  # should not raise
        comment.save()
        self.assertEqual(Comment.objects.count(), 1)

    def test_comment_with_case_and_matching_state(self):
        """
        python manage.py test app.tests.test_models.CommentModelTestCase.test_comment_with_case_and_matching_state
        A comment with both case and state pointing to the same case should be valid.
        """
        comment = Comment(
            text="Valid comment", case=self.case, state=self.state, created_by=self.user
        )
        comment.full_clean()  # should not raise
        comment.save()
        self.assertEqual(Comment.objects.count(), 1)

    # --- Invalid creation ---

    def test_comment_without_case_or_state_raises(self):
        """
        python manage.py test app.tests.test_models.CommentModelTestCase.test_comment_without_case_or_state_raises
        A comment with neither case nor state should raise ValidationError.
        """
        comment = Comment(text="Orphan comment", created_by=self.user)
        with self.assertRaises(ValidationError):
            comment.full_clean()

    def test_comment_with_mismatched_case_and_state_raises(self):
        """
        python manage.py test app.tests.test_models.CommentModelTestCase.test_comment_with_mismatched_case_and_state_raises
        A comment where state.case != comment.case should raise ValidationError.
        """
        other_case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_002)
        state_on_other_case = StateFactory(
            case=other_case, status="request_received", created_by=self.user
        )

        comment = Comment(
            text="Mismatched comment",
            case=self.case,  # case A
            state=state_on_other_case,  # state belongs to case B
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            comment.full_clean()
