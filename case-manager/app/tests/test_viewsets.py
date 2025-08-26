import json
import logging

from django.test import TestCase

# from app.models import Library, Sample, Subject, Individual, Project
# from app.tests.factories import LIBRARY_1, SUBJECT_1, SAMPLE_1, INDIVIDUAL_1, PROJECT_1, CONTACT_1
from app.tests.utils import insert_fixture_1, is_obj_exists

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# pragma: allowlist nextline secret
TEST_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJlbWFpbCI6ImpvaG4uZG9lQGV4YW1wbGUuY29tIn0.1XOO35Ozn1XNEj_W7RFefNfJnVm7C1pm7MCEBPbCkJ4"


def version_endpoint(ep: str):
    return "api/v1/" + ep


class ViewSetTestCase(TestCase):
    def setUp(self):
        insert_fixture_1()

    def test_get_api(self):
        """
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_get_api
        """
        # case

        logger.info(f"check API path for case")
        path = version_endpoint('case')
        response = self.client.get(f"/{path}/")
        self.assertEqual(response.status_code, 200,
                         "Ok status response is expected")

        result_response = response.data["results"]
        case = result_response[0]
        # Spot check external_entity_set
        self.assertEqual(len(case["external_entity_set"]), 2)
        self.assertEqual(case["external_entity_set"][0]["external_entity"]["service_name"], "metadata")
        self.assertIn(case["external_entity_set"][0]["added_via"], ['import', 'manual'])

        # Spot check user_set
        self.assertEqual(len(case["user_set"]), 1)
        self.assertEqual(case["user_set"][0]["description"], "lead")
        self.assertEqual(case["user_set"][0]["user"]["email"], "alice@umccr.org")

