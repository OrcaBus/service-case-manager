from django.test import TestCase
import logging

from case_manager.models.case import Case

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class CaseModelTests(TestCase):

    def test_minimal_case(self):
        """
        python manage.py test case_manager.tests.test_case.CaseModelTests.test_minimal_case
        """
        mock_case = Case()
        mock_case.case_name = "Test Case"
        mock_case.save()

        logger.info(mock_case)

        self.assertEqual(1, Case.objects.count())
