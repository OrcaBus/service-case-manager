from django.core.management import BaseCommand

from app.tests.utils import clear_all_data
from app.models import Case, User, State, Comment, ExternalEntity
from app.tests.factories import CASE_TITLE_001, USER_001, LIBRARY_001, LIBRARY_002


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    help = "Delete all DB data"

    def handle(self, *args, **options):
        clear_all_data()

        case = Case.objects.create(title=CASE_TITLE_001)
        user = User.objects.create(name=USER_001, email=f"{USER_001.lower()}@umccr.org")

        state_draft = State.objects.create(case=case, status="draft")
        state_pending = State.objects.create(case=case, status="pending")

        comment = Comment.objects.create(case=case, user=user)
        lib_1 = ExternalEntity.objects.create(**LIBRARY_001)
        case.external_entity_set.add(lib_1, through_defaults={"added_via": "import"})

        lib_2 = ExternalEntity.objects.create(**LIBRARY_002)
        case.external_entity_set.add(lib_2, through_defaults={"added_via": "manual"})

        case.user_set.add(user, through_defaults={"description": "lead"})
