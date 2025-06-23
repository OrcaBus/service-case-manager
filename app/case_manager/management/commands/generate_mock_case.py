from django.core.management import BaseCommand
from django.utils.timezone import make_aware

from datetime import datetime, timedelta
from case_manager.models.case import Case
from case_manager.tests.factories import CaseFactory


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    help = """
        Generate mock data and populate DB for local testing.
    """

    def handle(self, *args, **options):

        case1 = CaseFactory()
        case2 = CaseFactory()

        print("Done")
