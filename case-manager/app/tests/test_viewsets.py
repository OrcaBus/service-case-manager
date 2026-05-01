import json
import logging

from django.test import TestCase

from app.models import CaseExternalEntityLink, CaseUserLink
from app.tests.factories import (
    UserFactory,
    USER_002,
    INDIVIDUAL_001,
    ExternalEntityFactory,
)
from app.tests.utils import insert_fixture_1

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# pragma: allowlist nextline secret
TEST_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJlbWFpbCI6ImpvaG4uZG9lQGV4YW1wbGUuY29tIn0.1XOO35Ozn1XNEj_W7RFefNfJnVm7C1pm7MCEBPbCkJ4"


CASE_BASE_PATH = "api/v1/case"


class ViewSetTestCase(TestCase):
    def setUp(self):
        pass

    def test_get_api(self):
        """
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_get_api
        """
        # case
        insert_fixture_1()

        logger.info(f"check API path for case")
        response = self.client.get(f"/{CASE_BASE_PATH}/")
        self.assertEqual(response.status_code, 200, "Ok status response is expected")

        result_response = response.data["results"]
        case = result_response[0]
        # Spot check external_entity_set
        self.assertEqual(len(case["external_entity_set"]), 2)
        self.assertEqual(
            case["external_entity_set"][0]["external_entity"]["service_name"],
            "metadata",
        )

        # Spot check user_set
        self.assertEqual(len(case["user_set"]), 1)
        self.assertEqual(case["user_set"][0]["description"], "lead")
        self.assertEqual(case["user_set"][0]["user"]["email"], "alice@umccr.org")

    def test_link_relationship(self):
        """
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_link_relationship
        """
        case = insert_fixture_1()

        # case - user
        logger.info(f"check API path for case - user link")

        user_2 = UserFactory(name=USER_002)
        payload = {
            "email": user_2.email,
            "description": "lead",
        }
        response = self.client.post(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/user/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertIsNotNone(
            response.data, "CaseUserLink object is expected to be created"
        )
        expected_keys = {"id", "description", "timestamp", "case", "user"}
        self.assertTrue(
            expected_keys.issubset(response.data.keys()),
            "Expected keys are missing in the object",
        )
        user = case.user_set.get(name=USER_002)
        self.assertEqual(user.name, USER_002, "correct user name assigned")

        # case - external entity
        logger.info(f"check API path for case - external entity link")

        idv_1 = ExternalEntityFactory(**INDIVIDUAL_001)
        payload = {
            "external_entity": idv_1.orcabus_id,
        }
        response = self.client.post(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/external-entity/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        expected_keys = {"id", "timestamp", "case", "external_entity"}
        self.assertTrue(
            expected_keys.issubset(response.data.keys()),
            "Expected keys are missing in the object",
        )

        external_entity_3 = case.external_entity_set.get(alias=INDIVIDUAL_001["alias"])
        self.assertEqual(
            external_entity_3.alias,
            INDIVIDUAL_001["alias"],
            "correct external entity alias assigned",
        )
        self.assertEqual(
            case.external_entity_set.count(),
            3,
            "correct number of external entity linked to case",
        )

    def test_unlink_user(self):
        """
        Test unlinking a user from a case via DELETE.

        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_unlink_user
        """
        case = insert_fixture_1()
        user_2 = UserFactory(name=USER_002)
        # Link user
        CaseUserLink.objects.create(case=case, user=user_2, description="lead")
        self.assertEqual(case.user_set.count(), 2)

        response = self.client.delete(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/user/{user_2.orcabus_id}"
        )
        self.assertEqual(response.status_code, 204)
        case.refresh_from_db()
        self.assertEqual(case.user_set.filter(orcabus_id=user_2.orcabus_id).count(), 0)

    def test_unlink_external_entity(self):
        """
        Test unlinking an external entity from a case via DELETE.
        python manage.py test app.tests.test_viewsets.ViewSetTestCase.test_unlink_external_entity
        """
        case = insert_fixture_1()
        idv_1 = ExternalEntityFactory(**INDIVIDUAL_001)
        # Link external entity
        CaseExternalEntityLink.objects.create(case=case, external_entity=idv_1)
        self.assertEqual(case.external_entity_set.count(), 3)

        response = self.client.delete(
            f"/{CASE_BASE_PATH}/{case.orcabus_id}/external-entity/{idv_1.orcabus_id}"
        )
        self.assertEqual(response.status_code, 204)
        case.refresh_from_db()
        self.assertEqual(
            case.external_entity_set.filter(orcabus_id=idv_1.orcabus_id).count(), 0
        )
