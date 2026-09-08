import logging
import datetime
from django.core.exceptions import ValidationError
from django.test import TestCase
from .factories import USER_001, CASE_REQUEST_FORM_ID_001, CASE_REQUEST_FORM_ID_002
from .factories import UserFactory, StateFactory, CaseFactory, ExternalEntityFactory
from .utils import insert_fixture_1
from ..models import Case, CaseExternalEntityLink, CaseUserLink, Comment

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
        self.assertEqual(
            case.request_form_id,
            CASE_REQUEST_FORM_ID_001,
            "correct request form id assigned",
        )

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


class CaseManagerFilterByAnyLinkedLibrariesTestCase(TestCase):
    """
    python manage.py test app.tests.test_models.CaseManagerFilterByAnyLinkedLibrariesTestCase
    """

    def _link_library(self, case, alias):
        entity = ExternalEntityFactory(
            service_name="metadata", type="library", alias=alias
        )
        CaseExternalEntityLink.objects.create(case=case, external_entity=entity)
        return entity

    def test_matches_case_linked_to_all_requested_libraries(self):
        """
        python manage.py test app.tests.test_models.CaseManagerFilterByAnyLinkedLibrariesTestCase.test_matches_case_linked_to_all_requested_libraries
        A case linked to every requested library should match.
        """
        case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self._link_library(case, "1001")
        self._link_library(case, "1002")

        qs = Case.objects.filter_by_any_linked_libraries(
            Case.objects.all(), ["1001", "1002"]
        )

        self.assertEqual(list(qs), [case])

    def test_matches_case_linked_to_one_of_requested_libraries(self):
        """
        python manage.py test app.tests.test_models.CaseManagerFilterByAnyLinkedLibrariesTestCase.test_matches_case_linked_to_one_of_requested_libraries
        A case linked to just one of the requested libraries should match ("at least one").
        """
        case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self._link_library(case, "1001")  # only one of the two requested

        qs = Case.objects.filter_by_any_linked_libraries(
            Case.objects.all(), ["1001", "1002"]
        )

        self.assertEqual(list(qs), [case])

    def test_matches_case_with_extra_library(self):
        """
        python manage.py test app.tests.test_models.CaseManagerFilterByAnyLinkedLibrariesTestCase.test_matches_case_with_extra_library
        A case linked to a requested library PLUS extra libraries not requested should still match.
        """
        case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self._link_library(case, "1001")
        self._link_library(case, "1003")  # extra library not requested

        qs = Case.objects.filter_by_any_linked_libraries(
            Case.objects.all(), ["1001", "1002"]
        )

        self.assertEqual(list(qs), [case])

    def test_excludes_case_with_no_matching_library(self):
        """
        python manage.py test app.tests.test_models.CaseManagerFilterByAnyLinkedLibrariesTestCase.test_excludes_case_with_no_matching_library
        A case linked to none of the requested libraries should NOT match.
        """
        case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self._link_library(case, "9999")  # not in requested set

        qs = Case.objects.filter_by_any_linked_libraries(
            Case.objects.all(), ["1001", "1002"]
        )

        self.assertEqual(list(qs), [])


class CaseManagerFilterByLatestStateTestCase(TestCase):
    """
    python manage.py test app.tests.test_models.CaseManagerFilterByLatestStateTestCase
    """

    def setUp(self):
        self.user = UserFactory(name=USER_001)

    def _add_state(self, case, status, event_date, is_archived=False):
        """
        Create a State on the given case. event_date drives "latest" ordering
        (the subquery orders by -event_date, -event_time, -orcabus_id).
        """
        return StateFactory(
            case=case,
            status=status,
            created_by=self.user,
            event_date=event_date,
            is_archived=is_archived,
        )

    def test_matches_case_whose_latest_state_is_requested_status(self):
        """
        python manage.py test app.tests.test_models.CaseManagerFilterByLatestStateTestCase.test_matches_case_whose_latest_state_is_requested_status
        Only the latest (non-archived) state is considered; an earlier state with a
        matching status must not cause a match.
        """
        case = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        # Earlier state is 'sequencing_started', latest is 'sequencing_completed'.
        self._add_state(case, "sequencing_started", datetime.date(2024, 1, 1))
        self._add_state(case, "sequencing_completed", datetime.date(2024, 1, 2))

        # Latest is 'sequencing_completed' -> matches.
        qs = Case.objects.filter_by_latest_state(
            Case.objects.all(), ["sequencing_completed"]
        )
        self.assertEqual(list(qs), [case])

        # 'sequencing_started' is only an earlier state -> no match.
        qs = Case.objects.filter_by_latest_state(
            Case.objects.all(), ["sequencing_started"]
        )
        self.assertEqual(list(qs), [])

    def test_matches_multiple_statuses_or(self):
        """
        python manage.py test app.tests.test_models.CaseManagerFilterByLatestStateTestCase.test_matches_multiple_statuses_or
        Multiple requested statuses are OR-matched: a case matches if its latest
        state is ANY of the requested statuses.
        """
        case_a = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_001)
        self._add_state(case_a, "sequencing_started", datetime.date(2024, 1, 2))

        case_b = CaseFactory(request_form_id=CASE_REQUEST_FORM_ID_002)
        self._add_state(case_b, "bioinformatics_started", datetime.date(2024, 1, 2))

        # A third case at an unrequested status should be excluded.
        case_c = CaseFactory(request_form_id="case-003")
        self._add_state(case_c, "curation_started", datetime.date(2024, 1, 2))

        qs = Case.objects.filter_by_latest_state(
            Case.objects.all(),
            ["sequencing_started", "bioinformatics_started"],
        )

        self.assertCountEqual(list(qs), [case_a, case_b])
