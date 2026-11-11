from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import AuditLog, User
from accounts.services import log_audit
from coordination.models import DeliveryCoordination, SupplyGapReport
from facilities.models import Facility
from inventory.models import (
    Equipment,
    Product,
    StockBatch,
    StockMovement,
    TransferRequest,
)
from inventory.services import consume_stock, receive_stock
from vaccinations.models import (
    Patient,
    VaccinationRecord,
    VaccineFollowUp,
    VaccineSchedule,
)
from ai_engine.models import AIRecommendation

DEMO_PASSWORD = "Demo_Pass_123!"


class Command(BaseCommand):
    help = "Seed deterministic synthetic demo data for MedBridge Ethiopia."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Wipe existing data (superusers preserved) before seeding.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()
        elif Facility.objects.exists() or Product.objects.exists():
            self.stderr.write(
                self.style.WARNING(
                    "Data already exists. Re-run with --reset to wipe and reseed."
                )
            )
            return

        self._seed()
        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write("")
        self.stdout.write("Demo credentials (all users share this password):")
        self.stdout.write(f"    Password: {DEMO_PASSWORD}")
        self.stdout.write("")
        self.stdout.write("    demo_admin         SYSTEM_ADMIN")
        self.stdout.write("    demo_coord         CENTRAL_COORDINATOR")
        self.stdout.write("    mgr_bole           FACILITY_MANAGER @ Bole Health Center")
        self.stdout.write("    pharm_bole         PHARMACIST       @ Bole Health Center")
        self.stdout.write("    hw_bole            HEALTH_WORKER    @ Bole Health Center")
        self.stdout.write("    mgr_yeka           FACILITY_MANAGER @ Yeka Health Center")
        self.stdout.write("    pharm_yeka         PHARMACIST       @ Yeka Health Center")

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def _reset(self):
   

        with transaction.atomic():
            AIRecommendation.objects.all().delete()
            VaccinationRecord.objects.all().delete()
            VaccineFollowUp.objects.all().delete()
            Patient.objects.all().delete()
            VaccineSchedule.objects.all().delete()
            DeliveryCoordination.objects.all().delete()
            SupplyGapReport.objects.all().delete()
            TransferRequest.objects.all().delete()
            StockMovement.objects.all().delete()
            StockBatch.objects.all().delete()
            Equipment.objects.all().delete()
            Product.objects.all().delete()
            AuditLog.objects.all().delete()

            # Delete ALL demo accounts (including the seed superuser) plus any
            # user with a @demo.medbridge.local address, then any other
            # non-superuser the seed may have created earlier.
            User.objects.filter(email__endswith="@demo.medbridge.local").delete()
            User.objects.filter(is_superuser=False).delete()
            Facility.objects.all().delete()
        self.stdout.write("Cleared existing data (non-demo superusers preserved).")
    # ------------------------------------------------------------------
    # Seed
    # ------------------------------------------------------------------

    def _user(self, username, role, facility=None, superuser=False):
        if superuser:
            return User.objects.create_superuser(
                username=username,
                email=f"{username}@demo.medbridge.local",
                password=DEMO_PASSWORD,
                role=role,
                facility=facility,
            )
        return User.objects.create_user(
            username=username,
            email=f"{username}@demo.medbridge.local",
            password=DEMO_PASSWORD,
            role=role,
            facility=facility,
        )

    def _seed(self):
        # --- users ---
        admin = self._user("demo_admin", User.Role.SYSTEM_ADMIN, superuser=True)
        coord = self._user("demo_coord", User.Role.CENTRAL_COORDINATOR)

        # --- products ---
        para = Product.objects.create(
            name="Paracetamol",
            category=Product.Category.MEDICINE,
            strength="500mg",
            dosage_form="tablet",
            unit_of_measure="tablet",
        )
        amox = Product.objects.create(
            name="Amoxicillin",
            category=Product.Category.MEDICINE,
            strength="250mg",
            dosage_form="capsule",
            unit_of_measure="capsule",
        )
        bcg = Product.objects.create(
            name="BCG",
            category=Product.Category.VACCINE,
            requires_cold_chain=True,
            unit_of_measure="dose",
        )
        measles = Product.objects.create(
            name="Measles",
            category=Product.Category.VACCINE,
            requires_cold_chain=True,
            unit_of_measure="dose",
        )

        # --- facilities ---
        fa = Facility.objects.create(
            name="Bole Health Center",
            facility_type=Facility.FacilityType.HEALTH_CENTER,
            region="Addis Ababa",
            town="Bole",
            latitude="9.010000",
            longitude="38.760000",
            has_cold_chain=True,
            provides_vaccination_services=True,
            status=Facility.Status.APPROVED,
            reviewed_by=admin,
            submitted_by=admin,
            is_active=True,
        )
        fb = Facility.objects.create(
            name="Yeka Health Center",
            facility_type=Facility.FacilityType.HEALTH_CENTER,
            region="Addis Ababa",
            town="Yeka",
            latitude="9.030000",
            longitude="38.810000",
            has_cold_chain=True,
            provides_vaccination_services=True,
            status=Facility.Status.APPROVED,
            reviewed_by=admin,
            submitted_by=admin,
            is_active=True,
        )
        Facility.objects.create(
            name="Pending Demo Clinic",
            facility_type=Facility.FacilityType.CLINIC,
            region="Oromia",
            town="Adama",
            latitude="8.540000",
            longitude="39.270000",
            has_cold_chain=False,
            status=Facility.Status.PENDING,
            submitted_by=admin,
        )
        Facility.objects.create(
            name="Suspended Demo Clinic",
            facility_type=Facility.FacilityType.CLINIC,
            region="Amhara",
            town="Bahir Dar",
            latitude="11.590000",
            longitude="37.390000",
            has_cold_chain=False,
            status=Facility.Status.SUSPENDED,
            reviewed_by=admin,
            submitted_by=admin,
            is_active=True,
        )

        # --- facility users ---
        mgr_a = self._user("mgr_bole", User.Role.FACILITY_MANAGER, facility=fa)
        pharm_a = self._user("pharm_bole", User.Role.PHARMACIST, facility=fa)
        hw_a = self._user("hw_bole", User.Role.HEALTH_WORKER, facility=fa)
        mgr_b = self._user("mgr_yeka", User.Role.FACILITY_MANAGER, facility=fb)
        pharm_b = self._user("pharm_yeka", User.Role.PHARMACIST, facility=fb)

        # --- stock at Bole (source with surplus) ---
        receive_stock(
            facility=fa,
            product=para,
            batch_number="PARA-BOLE-2601",
            expiry_date=date.today() + timedelta(days=200),
            quantity=500,
            performed_by=pharm_a,
        )
        receive_stock(
            facility=fa,
            product=amox,
            batch_number="AMOX-BOLE-2601",
            expiry_date=date.today() + timedelta(days=45),  # near-expiry
            quantity=120,
            performed_by=pharm_a,
        )
        receive_stock(
            facility=fa,
            product=bcg,
            batch_number="BCG-BOLE-2601",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=pharm_a,
        )
        receive_stock(
            facility=fa,
            product=measles,
            batch_number="MEASLES-BOLE-2601",
            expiry_date=date.today() + timedelta(days=20),  # near-expiry demo
            quantity=60,
            performed_by=pharm_a,
        )

        # --- stock at Yeka (shortage) ---
        para_b, _, _ = receive_stock(
            facility=fb,
            product=para,
            batch_number="PARA-YEKA-2601",
            expiry_date=date.today() + timedelta(days=200),
            quantity=20,
            performed_by=pharm_b,
        )
        # Burn 20 units over 30 days → 2/day usage; usable stock now 0
        for _ in range(10):
            consume_stock(batch=para_b, quantity=2, performed_by=pharm_b)

        # --- vaccination schedules (approved source, deterministic) ---
        VaccineSchedule.objects.create(
            vaccine_product=bcg,
            dose_number=1,
            recommended_age_days=0,
            recommended_age_label="at birth",
            effective_from=date.today() - timedelta(days=90),
            source_name="Ethiopia EPI",
            source_version="2024.1",
            approved_by=admin,
            active=True,
        )
        VaccineSchedule.objects.create(
            vaccine_product=bcg,
            dose_number=2,
            minimum_interval_days=28,
            effective_from=date.today() - timedelta(days=90),
            source_name="Ethiopia EPI",
            source_version="2024.1",
            approved_by=admin,
            active=True,
        )
        VaccineSchedule.objects.create(
            vaccine_product=measles,
            dose_number=1,
            recommended_age_days=270,
            effective_from=date.today() - timedelta(days=90),
            source_name="Ethiopia EPI",
            source_version="2024.1",
            approved_by=admin,
            active=True,
        )

        # --- patients + follow-ups at Bole ---
        p1 = Patient.objects.create(
            facility=fa,
            patient_number="DEMO-BOLE-001",
            full_name="Demo Patient A1",
            date_of_birth=date.today() - timedelta(days=270),
            sex="MALE",
            created_by=hw_a,
            consent_given=True,
        )
        p2 = Patient.objects.create(
            facility=fa,
            patient_number="DEMO-BOLE-002",
            full_name="Demo Patient A2",
            date_of_birth=date.today() - timedelta(days=200),
            sex="FEMALE",
            created_by=hw_a,
            consent_given=True,
        )
        p3 = Patient.objects.create(
            facility=fa,
            patient_number="DEMO-BOLE-003",
            full_name="Demo Patient A3",
            date_of_birth=date.today() - timedelta(days=30),
            sex="UNKNOWN",
            created_by=hw_a,
            consent_given=True,
        )
        VaccineFollowUp.objects.create(
            patient=p1,
            vaccine_product=bcg,
            dose_number=1,
            due_date=date.today(),  # DUE today
        )
        VaccineFollowUp.objects.create(
            patient=p2,
            vaccine_product=bcg,
            dose_number=1,
            due_date=date.today() - timedelta(days=5),  # OVERDUE
        )
        VaccineFollowUp.objects.create(
            patient=p3,
            vaccine_product=bcg,
            dose_number=1,
            due_date=date.today() + timedelta(days=4),  # UPCOMING this week
        )

        # --- equipment ---
        Equipment.objects.create(
            facility=fa,
            name="Cold box",
            category="cold-chain",
            asset_identifier="CB-BOLE-01",
            quantity=2,
            condition=Equipment.Condition.OPERATIONAL,
            created_by=mgr_a,
        )
        Equipment.objects.create(
            facility=fa,
            name="Refrigerator",
            category="cold-chain",
            asset_identifier="FR-BOLE-01",
            quantity=1,
            condition=Equipment.Condition.NEEDS_MAINTENANCE,
            created_by=mgr_a,
        )
        Equipment.objects.create(
            facility=fb,
            name="Cold box",
            category="cold-chain",
            asset_identifier="CB-YEKA-01",
            quantity=1,
            condition=Equipment.Condition.OPERATIONAL,
            created_by=mgr_b,
        )

        # --- a documented phone-coordinated transfer (approved, pending dispatch) ---
        source_batch = StockBatch.objects.get(
            facility=fa, batch_number="PARA-BOLE-2601"
        )
        transfer = TransferRequest.objects.create(
            source_facility=fa,
            destination_facility=fb,
            product=para,
            source_batch=source_batch,
            quantity_requested=60,
            quantity_approved=60,
            priority=TransferRequest.Priority.HIGH,
            requested_by=pharm_b,
            approved_by=coord,
            status=TransferRequest.Status.APPROVED,
            notes="Demo transfer — ready for dispatch.",
        )
        source_batch.quantity_reserved = 60
        source_batch.save(update_fields=["quantity_reserved", "updated_at"])
        DeliveryCoordination.objects.create(
            transfer_request=transfer,
            transport_method="pickup",
            transport_provider="Local carrier",
            contact_person_name="Coordinator (phone)",
            contact_phone="+251900000000",
            transport_payer=DeliveryCoordination.Payer.CENTRAL,
            estimated_cost="250.00",
            currency="ETB",
            phone_coordination_status=DeliveryCoordination.PhoneStatus.CONFIRMED,
            delivery_status=DeliveryCoordination.DeliveryStatus.ARRANGED_BY_PHONE,
            coordinator=coord,
            notes="Pickup arranged for tomorrow morning.",
        )

        # --- one open supply gap (Yeka/Paracetamol) ---
        SupplyGapReport.objects.create(
            facility=fb,
            product=para,
            reporting_horizon_start=date.today(),
            reporting_horizon_end=date.today() + timedelta(days=30),
            projected_demand=60,
            usable_stock=0,
            reliable_incoming_quantity=0,
            uncovered_quantity=60,
            priority=SupplyGapReport.Priority.CRITICAL,
            status=SupplyGapReport.Status.OPEN,
            reason_summary=(
                "Projected demand 60 over 30-day horizon; usable stock 0; "
                "no reliable incoming stock."
            ),
        )

        log_audit(
            admin,
            "DEMO_SEEDED",
            "System",
            "",
            metadata={"seed": "demo_v1"},
        )