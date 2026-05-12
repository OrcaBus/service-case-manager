from django.core.management import BaseCommand

from handler.redcap_import import handler


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    """
    python manage.py import_redcap
    """

    def handle(self, *args, **options):
        handler(event={"after_date": "2026-05-08"}, _context=None)
