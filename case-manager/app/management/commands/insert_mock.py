from django.core.management import BaseCommand
from django.utils import timezone
from datetime import timedelta

from app.tests.utils import clear_all_data
from app.models import Case, User, State, Comment, ExternalEntity
from app.models.case import (
    CaseType,
    CaseStudyType,
    CaseUserLink,
    CaseExternalEntityLink,
)
from app.models.state import CaseStatus


# https://docs.djangoproject.com/en/5.0/howto/custom-management-commands/
class Command(BaseCommand):
    help = "Insert extensive mock data into the DB (clears existing data first)"

    def handle(self, *args, **options):
        clear_all_data()
        self.stdout.write("Cleared all existing data.")

        # ── Users ──────────────────────────────────────────────────────────────
        alice = User.objects.create(name="Alice", email="alice@umccr.org")
        bob = User.objects.create(name="Bob", email="bob@umccr.org")
        john = User.objects.create(name="John", email="john@umccr.org")
        eve = User.objects.create(name="Eve", email="eve@umccr.org")
        charlie = User.objects.create(name="Charlie", email="charlie@umccr.org")
        self.stdout.write(f"Created {User.objects.count()} users.")

        # ── External Entities ──────────────────────────────────────────────────
        lib_001 = ExternalEntity.objects.create(
            prefix="lib", service_name="metadata", alias="library-001", type="library"
        )
        lib_002 = ExternalEntity.objects.create(
            prefix="lib", service_name="metadata", alias="library-002", type="library"
        )
        lib_003 = ExternalEntity.objects.create(
            prefix="lib", service_name="metadata", alias="library-003", type="library"
        )
        lib_004 = ExternalEntity.objects.create(
            prefix="lib", service_name="metadata", alias="library-004", type="library"
        )
        idv_001 = ExternalEntity.objects.create(
            prefix="idv",
            service_name="metadata",
            alias="individual-001",
            type="individual",
        )
        idv_002 = ExternalEntity.objects.create(
            prefix="idv",
            service_name="metadata",
            alias="individual-002",
            type="individual",
        )
        seq_001 = ExternalEntity.objects.create(
            prefix="seq",
            service_name="sequence",
            alias="sequence-run-001",
            type="sequence_run",
        )
        seq_002 = ExternalEntity.objects.create(
            prefix="seq",
            service_name="sequence",
            alias="sequence-run-002",
            type="sequence_run",
        )
        wfr_001 = ExternalEntity.objects.create(
            prefix="wfr",
            service_name="workflow",
            alias="workflow-run-001",
            type="workflow_run",
        )
        self.stdout.write(
            f"Created {ExternalEntity.objects.count()} external entities."
        )

        now = timezone.now()

        # ── Case 1: WGTS Clinical — in bioinformatics ──────────────────────────
        case1 = Case.objects.create(
            request_form_id="mock-case-001",
            description="WGTS clinical case for subject SBJ00001",
            type=CaseType.WGTS,
            study_type=CaseStudyType.CLINICAL,
            is_report_required=True,
            is_nata_accredited=True,
            links={"trello": "https://trello.com/c/mock001"},
            alias=["SBJ00001", "PRJ00001"],
        )
        CaseUserLink.objects.create(case=case1, user=alice, description="Case Owner")
        CaseUserLink.objects.create(
            case=case1, user=bob, description="Bioinformatician"
        )
        CaseExternalEntityLink.objects.create(case=case1, external_entity=lib_001)
        CaseExternalEntityLink.objects.create(case=case1, external_entity=lib_002)
        CaseExternalEntityLink.objects.create(case=case1, external_entity=idv_001)
        CaseExternalEntityLink.objects.create(case=case1, external_entity=seq_001)

        s1_1 = State.objects.create(
            case=case1,
            status=CaseStatus.REQUEST_RECEIVED,
            created_by=alice,
            event_date=now - timedelta(days=30),
        )
        s1_2 = State.objects.create(
            case=case1,
            status=CaseStatus.WGTS_TUMOUR_SAMPLE_RECEIVED,
            created_by=alice,
            event_date=now - timedelta(days=25),
        )
        s1_3 = State.objects.create(
            case=case1,
            status=CaseStatus.SEQUENCING_STARTED,
            created_by=bob,
            event_date=now - timedelta(days=20),
        )
        s1_4 = State.objects.create(
            case=case1,
            status=CaseStatus.SEQUENCING_COMPLETED,
            created_by=bob,
            event_date=now - timedelta(days=15),
        )
        s1_5 = State.objects.create(
            case=case1,
            status=CaseStatus.BIOINFORMATICS_STARTED,
            created_by=bob,
            event_date=now - timedelta(days=10),
        )

        Comment.objects.create(
            case=case1,
            created_by=alice,
            text="Sample quality looks good. Proceeding to library prep.",
        )
        Comment.objects.create(
            case=case1,
            created_by=bob,
            text="Sequencing completed with high coverage. Starting bioinformatics pipeline.",
        )
        Comment.objects.create(
            state=s1_5,
            case=case1,
            created_by=bob,
            text="DRAGEN pipeline triggered for WGS + WTS analysis.",
        )

        # ── Case 2: WGTS Research — completed ─────────────────────────────────
        case2 = Case.objects.create(
            request_form_id="mock-case-002",
            description="WGTS research case for subject SBJ00002",
            type=CaseType.WGTS,
            study_type=CaseStudyType.RESEARCH,
            is_report_required=False,
            is_nata_accredited=False,
            alias=["SBJ00002", "PRJ00002"],
        )
        CaseUserLink.objects.create(case=case2, user=john, description="Case Owner")
        CaseUserLink.objects.create(case=case2, user=eve, description="Curator")
        CaseExternalEntityLink.objects.create(case=case2, external_entity=lib_003)
        CaseExternalEntityLink.objects.create(case=case2, external_entity=idv_002)
        CaseExternalEntityLink.objects.create(case=case2, external_entity=seq_002)
        CaseExternalEntityLink.objects.create(case=case2, external_entity=wfr_001)

        s2_1 = State.objects.create(
            case=case2,
            status=CaseStatus.REQUEST_RECEIVED,
            created_by=john,
            event_date=now - timedelta(days=60),
        )
        s2_2 = State.objects.create(
            case=case2,
            status=CaseStatus.WGTS_TUMOUR_SAMPLE_RECEIVED,
            created_by=john,
            event_date=now - timedelta(days=55),
        )
        s2_3 = State.objects.create(
            case=case2,
            status=CaseStatus.SEQUENCING_COMPLETED,
            created_by=john,
            event_date=now - timedelta(days=45),
        )
        s2_4 = State.objects.create(
            case=case2,
            status=CaseStatus.BIOINFORMATICS_COMPLETED,
            created_by=eve,
            event_date=now - timedelta(days=30),
        )
        s2_5 = State.objects.create(
            case=case2,
            status=CaseStatus.CURATION_COMPLETED,
            created_by=eve,
            event_date=now - timedelta(days=15),
        )
        s2_6 = State.objects.create(
            case=case2,
            status=CaseStatus.COMPLETED,
            created_by=john,
            event_date=now - timedelta(days=5),
        )

        Comment.objects.create(
            case=case2,
            created_by=john,
            text="Research case — no clinical report needed.",
        )
        Comment.objects.create(
            state=s2_4,
            case=case2,
            created_by=eve,
            text="All bioinformatics QC metrics passed. Moving to curation.",
        )
        Comment.objects.create(
            state=s2_6,
            case=case2,
            created_by=john,
            text="Case completed and results archived.",
        )

        # ── Case 3: ctTSO Clinical — curation in progress ─────────────────────
        case3 = Case.objects.create(
            request_form_id="mock-case-003",
            description="ctTSO550 clinical case for subject SBJ00003",
            type=CaseType.CTTSO,
            study_type=CaseStudyType.CLINICAL,
            is_report_required=True,
            is_nata_accredited=True,
            links={"trello": "https://trello.com/c/mock003"},
            alias=["SBJ00003"],
        )
        CaseUserLink.objects.create(case=case3, user=alice, description="Case Owner")
        CaseUserLink.objects.create(case=case3, user=charlie, description="Curator")
        CaseExternalEntityLink.objects.create(case=case3, external_entity=lib_004)
        CaseExternalEntityLink.objects.create(case=case3, external_entity=idv_001)

        s3_1 = State.objects.create(
            case=case3,
            status=CaseStatus.REQUEST_RECEIVED,
            created_by=alice,
            event_date=now - timedelta(days=20),
        )
        s3_2 = State.objects.create(
            case=case3,
            status=CaseStatus.CTTSO_SAMPLE_RECEIVED,
            created_by=alice,
            event_date=now - timedelta(days=18),
        )
        s3_3 = State.objects.create(
            case=case3,
            status=CaseStatus.SEQUENCING_COMPLETED,
            created_by=bob,
            event_date=now - timedelta(days=12),
        )
        s3_4 = State.objects.create(
            case=case3,
            status=CaseStatus.BIOINFORMATICS_COMPLETED,
            created_by=bob,
            event_date=now - timedelta(days=7),
        )
        s3_5 = State.objects.create(
            case=case3,
            status=CaseStatus.CURATION_STARTED,
            created_by=charlie,
            event_date=now - timedelta(days=3),
        )

        Comment.objects.create(
            case=case3,
            created_by=alice,
            text="Urgent clinical case — expedite where possible.",
        )
        Comment.objects.create(
            state=s3_3,
            case=case3,
            created_by=bob,
            text="ctTSO sequencing passed QC. Variant calling pipeline submitted.",
        )
        Comment.objects.create(
            state=s3_5,
            case=case3,
            created_by=charlie,
            text="Starting curation — reviewing somatic variants.",
        )

        # ── Case 4: WGTS Clinical — failed with library issue ──────────────────
        case4 = Case.objects.create(
            request_form_id="mock-case-004",
            description="WGTS clinical case that failed due to library prep issues",
            type=CaseType.WGTS,
            study_type=CaseStudyType.CLINICAL,
            is_report_required=True,
            is_nata_accredited=True,
            alias=["SBJ00004"],
        )
        CaseUserLink.objects.create(case=case4, user=bob, description="Case Owner")
        CaseExternalEntityLink.objects.create(case=case4, external_entity=lib_001)
        CaseExternalEntityLink.objects.create(case=case4, external_entity=idv_002)

        s4_1 = State.objects.create(
            case=case4,
            status=CaseStatus.REQUEST_RECEIVED,
            created_by=bob,
            event_date=now - timedelta(days=10),
        )
        s4_2 = State.objects.create(
            case=case4,
            status=CaseStatus.WGTS_TUMOUR_SAMPLE_RECEIVED,
            created_by=bob,
            event_date=now - timedelta(days=9),
        )
        s4_3 = State.objects.create(
            case=case4,
            status=CaseStatus.LIBRARY_PARTIALLY_FAILED,
            created_by=bob,
            event_date=now - timedelta(days=7),
        )
        s4_4 = State.objects.create(
            case=case4,
            status=CaseStatus.FAILED,
            created_by=bob,
            event_date=now - timedelta(days=5),
        )

        Comment.objects.create(
            state=s4_3,
            case=case4,
            created_by=bob,
            text="Library prep failed for WGS component. Only WTS library succeeded.",
        )
        Comment.objects.create(
            state=s4_4,
            case=case4,
            created_by=bob,
            text="Case marked as failed. Sample insufficient to re-attempt.",
        )

        # ── Case 5: ctTSO Research — just received ─────────────────────────────
        case5 = Case.objects.create(
            request_form_id="mock-case-005",
            description="ctTSO research case for novel biomarker study",
            type=CaseType.CTTSO,
            study_type=CaseStudyType.RESEARCH,
            is_report_required=False,
            is_nata_accredited=False,
            alias=["SBJ00005", "STUDY-BIOMARKER-42"],
        )
        CaseUserLink.objects.create(case=case5, user=eve, description="Case Owner")
        CaseUserLink.objects.create(
            case=case5, user=charlie, description="Bioinformatician"
        )
        CaseExternalEntityLink.objects.create(case=case5, external_entity=lib_002)
        CaseExternalEntityLink.objects.create(case=case5, external_entity=seq_001)

        s5_1 = State.objects.create(
            case=case5,
            status=CaseStatus.REQUEST_RECEIVED,
            created_by=eve,
            event_date=now - timedelta(days=2),
        )

        Comment.objects.create(
            case=case5,
            created_by=eve,
            text="New research case for biomarker discovery cohort. Low priority.",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nMock data inserted successfully!\n"
                f"  Cases:            {Case.objects.count()}\n"
                f"  Users:            {User.objects.count()}\n"
                f"  States:           {State.objects.count()}\n"
                f"  Comments:         {Comment.objects.count()}\n"
                f"  External Entities:{ExternalEntity.objects.count()}\n"
            )
        )
