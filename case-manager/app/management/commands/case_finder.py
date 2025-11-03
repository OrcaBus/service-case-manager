from django.core.management import BaseCommand

from app.service.case_finder import create_case_from_library_findings


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    """
    python manage.py case_finder
    """

    help = "Delete all DB data"

    def handle(self, *args, **options):
        create_case_from_library_findings()
