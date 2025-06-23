from django.core.management import BaseCommand

from case_manager.models.case import Case
from case_manager.models.case_state import CaseState
from case_manager.models.linked_entity import LinkedEntity
from case_manager.models.case_comment import CaseComment


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    help = "Delete all DB data"

    def handle(self, *args, **options):
        Case.objects.all().delete()
        # CaseComment.objects.all().delete()
        CaseState.objects.all().delete()
        # LinkedEntity.objects.all().delete()

        print("Done")
