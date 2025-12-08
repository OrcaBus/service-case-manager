from django.core.management import BaseCommand

from app.service.case_finder import cttso_case_builder, wgts_case_builder


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    """
    python manage.py case_finder2
    """

    def handle(self, *args, **options):

        cttso_case_builder()
        wgts_case_builder()
