from django.core.management import BaseCommand

from handler.metadata_manager_linking import handler


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    """
    python manage.py link_metadata_via_event
    """

    def handle(self, *args, **options):
        handler(
            event={
                "version": "0",
                "id": "a3f85c21-7b4d-4e19-bc62-9f1d2a0e83c7",
                "detail-type": "MetadataStateChange",
                "source": "orcabus.metadatamanager",
                "account": "0123456789",
                "time": "2026-05-15T04:35:01Z",
                "region": "ap-southeast-2",
                "resources": [],
                "detail": {
                    "model": "LIBRARY",
                    "action": "CREATE",
                    "refId": "lib.01JQZMKATBPFXGQV3HR72NDSPL",
                    "data": {
                        "orcabusId": "lib.01JQZMKATBPFXGQV3HR72NDSPL",
                        "libraryId": "L9403817",
                        "requestFormId": "1000000",
                    },
                },
            },
            context=None,
        )
