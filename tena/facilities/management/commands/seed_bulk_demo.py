"""
Bulk demo data seeder. NON-DESTRUCTIVE: only adds rows, never edits or
deletes existing data. Safe to re-run (it exits early if already seeded).

Adds: facilities in every status, users for each, extra products, batches
(including expired/quarantined/damaged stock), consumption/wastage/adjustment
history, transfers in every workflow status, delivery coordination records,
supply gaps in every status, vaccine schedules, patients, vaccination records,
follow-ups in every status, equipment, and AI recommendations.

Run:  python manage.py seed_bulk_demo
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import User
from accounts.services import log_audit
from ai_engine.models import AIRecommendation
from coordination.models import DeliveryCoordination, SupplyGapReport
from facilities.models import Facility
from inventory.models import (
    Equipment,
    Product,
    StockBatch,
    StockMovement,
    TransferRequest,
)
from inventory.services import (
    adjust_stock,
    consume_stock,
    receive_stock,
    record_wastage,
)
from inventory.transfers import (
    approve_transfer,
    cancel_transfer,
    create_transfer_request,
    dispatch_transfer,
    receive_transfer,
    reject_transfer,
)
from vaccinations.models import (
    Patient,
    VaccineFollowUp,
    VaccineSchedule,
)
from vaccinations.services import (
    cancel_follow_up,
    mark_review_required,
    record_contact,
    record_vaccination,
)

DEMO_PASSWORD = "Demo_Pass_123!"
MARKER_FACILITY = "St. Paul's Hospital"
EMAIL_DOMAIN = "@demo.medbridge.local"


def d(days_from_now):
    return date.today() + timedelta(days=days_from_now)


def dt(days_ago, hour=9):
    base = timezone.now() - timedelta(days=days_ago)
    return base.replace(hour=hour % 24, minute=0, second=0, microsecond=0)


class Command(BaseCommand):
    help = "Seed additional bulk demo data for testing every feature (non-destructive)."

    def handle(self, *args, **options):
        if Facility.objects.filter(name=MARKER_FACILITY).exists():
            self.stderr.write(
                self.style.WARNING(
                    f"Bulk demo data already seeded (found '{MARKER_FACILITY}'). Nothing to do."
                )
            )
            return

        with transaction.atomic():
            products = self._seed_products()
            people = self._seed_facilities_and_users()
            self._seed_schedules(products)
            stock = self._seed_stock(products, people)
            self._seed_consumption_history(people, stock)
            self._seed_transfers(products, people, stock)
            gaps = self._seed_gaps(products, people)
            self._seed_patients_and_vaccinations(products, people, stock)
            self._seed_equipment(people)
            self._seed_ai(products, people, gaps)
            log_audit(
                people["demo_admin"],
                "DEMO_BULK_SEEDED",
                "System",
                "",
                metadata={"seed": "bulk_demo_v1"},
            )

        self.stdout.write(self.style.SUCCESS("Bulk demo data seeded."))
        self.stdout.write("")
        self.stdout.write(f"  Facilities:  {Facility.objects.count()}")
        self.stdout.write(f"  Users:       {User.objects.count()}")
        self.stdout.write(f"  Products:    {Product.objects.count()}")
        self.stdout.write(f"  Batches:     {StockBatch.objects.count()}")
        self.stdout.write(f"  Movements:   {StockMovement.objects.count()}")
        self.stdout.write(f"  Transfers:   {TransferRequest.objects.count()}")
        self.stdout.write(f"  Supply gaps: {SupplyGapReport.objects.count()}")
        self.stdout.write(f"  Patients:    {Patient.objects.count()}")
        self.stdout.write(f"  Follow-ups:  {VaccineFollowUp.objects.count()}")
        self.stdout.write(f"  AI recs:     {AIRecommendation.objects.count()}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _user(self, username, role, facility=None):
        return User.objects.create_user(
            username=username,
            email=f"{username}{EMAIL_DOMAIN}",
            password=DEMO_PASSWORD,
            role=role,
            facility=facility,
        )

    def _usable(self, facility, product):
        agg = StockBatch.objects.filter(facility=facility, product=product).aggregate(
            total=Sum("quantity_available")
        )
        return agg["total"] or 0

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def _seed_products(self):
        cold = {
            "requires_cold_chain": True,
            "storage_min_temperature": "2.00",
            "storage_max_temperature": "8.00",
        }
        specs = [
            ("PARA", "Paracetamol", Product.Category.MEDICINE,
             {"strength": "500mg", "dosage_form": "tablet", "unit_of_measure": "tablet"}),
            ("AMOX", "Amoxicillin", Product.Category.MEDICINE,
             {"strength": "250mg", "dosage_form": "capsule", "unit_of_measure": "capsule"}),
            ("ORS", "Oral Rehydration Salts", Product.Category.MEDICINE,
             {"dosage_form": "sachet", "unit_of_measure": "sachet"}),
            ("CEFI", "Ceftriaxone", Product.Category.MEDICINE,
             {"strength": "1g", "dosage_form": "injection", "unit_of_measure": "vial"}),
            ("IBU", "Ibuprofen", Product.Category.MEDICINE,
             {"strength": "400mg", "dosage_form": "tablet", "unit_of_measure": "tablet"}),
            ("METRO", "Metronidazole", Product.Category.MEDICINE,
             {"strength": "250mg", "dosage_form": "tablet", "unit_of_measure": "tablet"}),
            ("COTRI", "Cotrimoxazole", Product.Category.MEDICINE,
             {"strength": "480mg", "dosage_form": "tablet", "unit_of_measure": "tablet"}),
            ("BCG", "BCG", Product.Category.VACCINE, cold),
            ("MEASLES", "Measles", Product.Category.VACCINE, cold),
            ("OPV", "Oral Polio Vaccine", Product.Category.VACCINE, cold),
            ("PENTA", "Pentavalent (DPT-HepB-Hib)", Product.Category.VACCINE, cold),
            ("ROTA", "Rotavirus Vaccine", Product.Category.VACCINE, cold),
            ("PCV", "Pneumococcal Vaccine (PCV)", Product.Category.VACCINE, cold),
            ("TT", "Tetanus Toxoid", Product.Category.VACCINE, cold),
        ]
        products = {}
        for key, name, category, kwargs in specs:
            product, _ = Product.objects.get_or_create(
                name=name, defaults={"category": category, **kwargs}
            )
            products[key] = product
        return products

    # ------------------------------------------------------------------
    # Facilities + users
    # ------------------------------------------------------------------

    def _seed_facilities_and_users(self):
        demo_admin = User.objects.get(username="demo_admin")
        demo_coord = User.objects.get(username="demo_coord")

        applicant_adama = self._user("applicant_adama", User.Role.HEALTH_WORKER)
        applicant_gondar = self._user("applicant_gondar", User.Role.HEALTH_WORKER)
        hw_yeka = self._user(
            "hw_yeka", User.Role.HEALTH_WORKER,
            facility=Facility.objects.get(name="Yeka Health Center"),
        )

        stp = Facility.objects.create(
            name="St. Paul's Hospital",
            facility_type=Facility.FacilityType.HOSPITAL,
            registration_number="AA-SPH-1143",
            region="Addis Ababa", zone="Addis Ababa", woreda="04", kebele="08",
            town="Addis Ababa", address="Gullele, near St. Paul's Church",
            landmark="St. Paul's roundabout",
            latitude="9.045200", longitude="38.748200",
            contact_phone="+251118752100",
            storage_capacity_notes="Main pharmacy cold room + 2 ward fridges.",
            has_cold_chain=True,
            cold_chain_notes="Cold room with 24h generator backup.",
            provides_vaccination_services=True,
            status=Facility.Status.APPROVED,
            reviewed_by=demo_admin, submitted_by=demo_admin,
        )
        haw = Facility.objects.create(
            name="Hawassa Referral Hospital",
            facility_type=Facility.FacilityType.HOSPITAL,
            registration_number="SID-HRH-2077",
            region="Sidama", town="Hawassa", woreda="02",
            address="Lake Awassa road", landmark="Amora Gedel",
            latitude="7.062200", longitude="38.476400",
            contact_phone="+251466206000",
            storage_capacity_notes="Regional vaccine store on site.",
            has_cold_chain=True, cold_chain_notes="Solar direct-drive fridge.",
            provides_vaccination_services=True,
            status=Facility.Status.APPROVED,
            reviewed_by=demo_admin, submitted_by=demo_admin,
        )
        jim = Facility.objects.create(
            name="Jimma Community Pharmacy",
            facility_type=Facility.FacilityType.PHARMACY,
            registration_number="ORO-JCP-3310",
            region="Oromia", town="Jimma", woreda="01",
            address="Merkato road", latitude="7.676100", longitude="36.834900",
            contact_phone="+251471112233",
            storage_capacity_notes="Two medicine fridges.",
            has_cold_chain=True, provides_vaccination_services=False,
            status=Facility.Status.APPROVED,
            reviewed_by=demo_admin, submitted_by=demo_admin,
        )
        dire = Facility.objects.create(
            name="Dire Dawa Health Center",
            facility_type=Facility.FacilityType.HEALTH_CENTER,
            registration_number="DIR-DHC-1002",
            region="Dire Dawa", town="Dire Dawa", woreda="03",
            latitude="9.593100", longitude="41.866100",
            has_cold_chain=False, provides_vaccination_services=True,
            status=Facility.Status.SUSPENDED,
            reviewed_by=demo_admin, reviewed_at=dt(4),
            review_note="Repeated temperature excursions unaddressed during the last inspection.",
            submitted_by=demo_admin,
        )
        Facility.objects.create(
            name="Adama Health Center",
            facility_type=Facility.FacilityType.HEALTH_CENTER,
            region="Oromia", town="Adama", woreda="02", kebele="06",
            latitude="8.542100", longitude="39.268900",
            contact_phone="+251223331122",
            has_cold_chain=True, provides_vaccination_services=True,
            status=Facility.Status.PENDING,
            submitted_by=applicant_adama,
        )
        Facility.objects.create(
            name="Gondar Health Center",
            facility_type=Facility.FacilityType.HEALTH_CENTER,
            region="Amhara", town="Gondar", woreda="05",
            latitude="12.609400", longitude="37.466300",
            has_cold_chain=True, provides_vaccination_services=True,
            status=Facility.Status.REJECTED,
            reviewed_by=demo_admin, reviewed_at=dt(3),
            review_note=("Registration number could not be verified with the regional "
                         "bureau. Please resubmit with the licence document."),
            submitted_by=applicant_gondar,
        )

        def staff(facility, prefix, roles):
            return {
                key: self._user(f"{prefix}_{key}", role, facility=facility)
                for key, role in roles.items()
            }

        stp_users = staff(stp, "stp", {
            "mgr": User.Role.FACILITY_MANAGER,
            "pharm": User.Role.PHARMACIST,
            "inv": User.Role.INVENTORY_STAFF,
            "phstaff": User.Role.PHARMACY_STAFF,
            "hw": User.Role.HEALTH_WORKER,
            "hw2": User.Role.HEALTH_WORKER,
        })
        haw_users = staff(haw, "haw", {
            "mgr": User.Role.FACILITY_MANAGER,
            "pharm": User.Role.PHARMACIST,
            "hw": User.Role.HEALTH_WORKER,
        })
        jim_users = staff(jim, "jim", {
            "mgr": User.Role.FACILITY_MANAGER,
            "pharm": User.Role.PHARMACIST,
        })
        dire_users = staff(dire, "dire", {
            "mgr": User.Role.FACILITY_MANAGER,
        })

        return {
            "demo_admin": demo_admin,
            "demo_coord": demo_coord,
            "hw_yeka": hw_yeka,
            "applicant_adama": applicant_adama,
            "applicant_gondar": applicant_gondar,
            "stp": {"facility": stp, **stp_users},
            "haw": {"facility": haw, **haw_users},
            "jim": {"facility": jim, **jim_users},
            "dire": {"facility": dire, **dire_users},
        }

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------

    def _seed_schedules(self, products):
        demo_admin = User.objects.get(username="demo_admin")
        rows = [
            ("BCG", 1, 0, "At birth", None),
            ("OPV", 1, 42, "6 weeks", None),
            ("OPV", 2, None, "", 28),
            ("OPV", 3, None, "", 28),
            ("PENTA", 1, 42, "6 weeks", None),
            ("PENTA", 2, None, "", 28),
            ("PENTA", 3, None, "", 28),
            ("ROTA", 1, 42, "6 weeks", None),
            ("ROTA", 2, None, "", 28),
            ("PCV", 1, 42, "6 weeks", None),
            ("PCV", 2, None, "", 28),
            ("PCV", 3, None, "", 28),
            ("TT", 1, 270, "9 months", None),
            ("TT", 2, None, "", 28),
            ("MEASLES", 1, 270, "9 months", None),
            ("MEASLES", 2, None, "", 28),
        ]
        for key, dose, age, label, interval in rows:
            existing = VaccineSchedule.objects.filter(
                vaccine_product=products[key], dose_number=dose
            ).first()
            if existing is not None:
                continue
            VaccineSchedule.objects.create(
                vaccine_product=products[key],
                dose_number=dose,
                recommended_age_days=age,
                recommended_age_label=label,
                minimum_interval_days=interval,
                effective_from=d(-90),
                source_name="Ethiopia EPI",
                source_version="2024.1",
                approved_by=demo_admin,
                active=True,
            )

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    # facility key -> list of (product_key, batch_number, expiry_days, qty)
    STOCK_PLAN = {
        "bole": [
            ("PARA", "PARA-BOLE-2602", 240, 400),
            ("AMOX", "AMOX-BOLE-2602", 130, 200),
            ("ORS", "ORS-BOLE-2601", 300, 300),
            ("CEFI", "CEFI-BOLE-2601", 70, 80),
            ("IBU", "IBU-BOLE-2601", 180, 150),
            ("METRO", "METRO-BOLE-2601", 100, 120),
            ("COTRI", "COTRI-BOLE-2601", 160, 140),
            ("BCG", "BCG-BOLE-2602", 220, 200),
            ("MEASLES", "MEASLES-BOLE-2602", 35, 150),
            ("OPV", "OPV-BOLE-2601", 150, 200),
            ("PENTA", "PENTA-BOLE-2601", 140, 180),
            ("ROTA", "ROTA-BOLE-2601", 120, 160),
            ("PCV", "PCV-BOLE-2601", 130, 170),
            ("TT", "TT-BOLE-2601", 170, 140),
        ],
        "yeka": [
            ("PARA", "PARA-YEKA-2602", 220, 120),
            ("AMOX", "AMOX-YEKA-2602", 150, 100),
            ("ORS", "ORS-YEKA-2601", 280, 150),
            ("IBU", "IBU-YEKA-2601", 190, 90),
            ("COTRI", "COTRI-YEKA-2601", 140, 110),
            ("MEASLES", "MEASLES-YEKA-2601", 60, 100),
            ("BCG", "BCG-YEKA-2601", 200, 120),
            ("OPV", "OPV-YEKA-2601", 130, 110),
            ("PENTA", "PENTA-YEKA-2601", 135, 100),
            ("ROTA", "ROTA-YEKA-2601", 115, 90),
            ("PCV", "PCV-YEKA-2601", 125, 95),
        ],
        "stp": [
            ("PARA", "PARA-STP-2601", 260, 350),
            ("AMOX", "AMOX-STP-2601", 140, 220),
            ("ORS", "ORS-STP-2601", 310, 260),
            ("CEFI", "CEFI-STP-2601", 80, 120),
            ("IBU", "IBU-STP-2601", 170, 130),
            ("METRO", "METRO-STP-2601", 110, 140),
            ("COTRI", "COTRI-STP-2601", 150, 160),
            ("BCG", "BCG-STP-2601", 210, 160),
            ("MEASLES", "MEAS-STP-2601", 55, 120),
            ("OPV", "OPV-STP-2601", 120, 150),
            ("PENTA", "PENTA-STP-2601", 150, 170),
            ("ROTA", "ROTA-STP-2601", 125, 140),
            ("PCV", "PCV-STP-2601", 135, 150),
            ("TT", "TT-STP-2601", 160, 130),
        ],
        "haw": [
            ("PARA", "PARA-HAW-2601", 230, 280),
            ("AMOX", "AMOX-HAW-2601", 120, 180),
            ("ORS", "ORS-HAW-2601", 290, 220),
            ("CEFI", "CEFI-HAW-2601", 65, 90),
            ("IBU", "IBU-HAW-2601", 160, 100),
            ("METRO", "METRO-HAW-2601", 95, 110),
            ("COTRI", "COTRI-HAW-2601", 170, 150),
            ("BCG", "BCG-HAW-2601", 190, 130),
            ("MEASLES", "MEASLES-HAW-2601", 45, 110),
            ("OPV", "OPV-HAW-2601", 140, 120),
            ("PENTA", "PENTA-HAW-2601", 145, 150),
            ("ROTA", "ROTA-HAW-2601", 118, 130),
            ("PCV", "PCV-HAW-2601", 128, 140),
            ("TT", "TT-HAW-2601", 155, 120),
        ],
        "jim": [
            ("PARA", "PARA-JIM-2601", 210, 200),
            ("AMOX", "AMOX-JIM-2601", 110, 140),
            ("ORS", "ORS-JIM-2601", 300, 180),
            ("IBU", "IBU-JIM-2601", 175, 120),
            ("METRO", "METRO-JIM-2601", 90, 80),
            ("COTRI", "COTRI-JIM-2601", 130, 90),
            ("CEFI", "CEFI-JIM-2601", 60, 50),
        ],
    }

    # (facility, product_key, number, expiry_days, qty, action)
    PROBLEM_BATCHES = [
        ("bole", "AMOX", "AMOX-BOLE-EXP", -12, 40, "wastage"),
        ("bole", "METRO", "METRO-BOLE-QUAR", 90, 30, "quarantine"),
        ("bole", "ORS", "ORS-BOLE-ADJ", 200, 100, "adjust"),
        ("yeka", "PARA", "PARA-YEKA-EXP", -6, 20, "expired_status"),
        ("yeka", "ORS", "ORS-YEKA-ADJ", 260, 60, "adjust"),
        ("haw", "OPV", "OPV-HAW-EXC", 100, 25, "excursion"),
        ("jim", "ORS", "ORS-JIM-DAMG", 200, 20, "damaged"),
    ]

    def _seed_stock(self, products, people):
        facilities = {
            "bole": (Facility.objects.get(name="Bole Health Center"),
                     User.objects.get(username="pharm_bole")),
            "yeka": (Facility.objects.get(name="Yeka Health Center"),
                     User.objects.get(username="pharm_yeka")),
            "stp": (people["stp"]["facility"], people["stp"]["pharm"]),
            "haw": (people["haw"]["facility"], people["haw"]["pharm"]),
            "jim": (people["jim"]["facility"], people["jim"]["pharm"]),
        }
        demo_admin = people["demo_admin"]
        batches = {key: {} for key in facilities}
        for fkey, (facility, performer) in facilities.items():
            for pkey, number, expiry_days, qty in self.STOCK_PLAN[fkey]:
                batch, _, _ = receive_stock(
                    facility=facility,
                    product=products[pkey],
                    batch_number=number,
                    expiry_date=d(expiry_days),
                    quantity=qty,
                    source_reference="Bulk demo intake",
                    performed_by=performer,
                )
                batches[fkey][pkey] = batch

        status_map = {
            "quarantine": StockBatch.StorageStatus.QUARANTINED,
            "excursion": StockBatch.StorageStatus.TEMPERATURE_EXCURSION,
            "damaged": StockBatch.StorageStatus.DAMAGED,
            "expired_status": StockBatch.StorageStatus.EXPIRED,
        }
        for fkey, pkey, number, expiry_days, qty, action in self.PROBLEM_BATCHES:
            facility, performer = facilities[fkey]
            batch, _, _ = receive_stock(
                facility=facility,
                product=products[pkey],
                batch_number=number,
                expiry_date=d(expiry_days),
                quantity=qty,
                source_reference="Bulk demo intake",
                performed_by=performer,
            )
            if action in status_map:
                batch.storage_status = status_map[action]
                batch.save(update_fields=["storage_status", "updated_at"])
            elif action == "wastage":
                record_wastage(
                    batch=batch, quantity=25,
                    reason="Expired stock disposal (bulk demo)",
                    performed_by=performer,
                )
            elif action == "adjust":
                adjust_stock(
                    batch=batch, quantity=10, direction="IN",
                    reason="Physical count correction (bulk demo)",
                    performed_by=demo_admin,
                )
        return batches

    # (facility, product_key, repeats, qty_each)
    CONSUMPTION_PLAN = [
        ("bole", "PARA", 3, 12), ("bole", "AMOX", 2, 8), ("bole", "ORS", 2, 10),
        ("bole", "IBU", 2, 6), ("bole", "METRO", 2, 5), ("bole", "COTRI", 2, 7),
        ("bole", "CEFI", 1, 4),
        ("yeka", "PARA", 2, 10), ("yeka", "ORS", 2, 8), ("yeka", "IBU", 1, 5),
        ("stp", "PARA", 3, 10), ("stp", "AMOX", 2, 7), ("stp", "CEFI", 2, 3),
        ("stp", "ORS", 1, 9),
        ("haw", "PARA", 2, 9), ("haw", "AMOX", 2, 6), ("haw", "METRO", 1, 4),
        ("jim", "PARA", 2, 6), ("jim", "IBU", 2, 4),
    ]

    def _seed_consumption_history(self, people, batches):
        performers = {
            "bole": User.objects.get(username="pharm_bole"),
            "yeka": User.objects.get(username="pharm_yeka"),
            "stp": people["stp"]["pharm"],
            "haw": people["haw"]["pharm"],
            "jim": people["jim"]["pharm"],
        }
        for fkey, pkey, repeats, qty in self.CONSUMPTION_PLAN:
            batch = batches[fkey][pkey]
            for i in range(repeats):
                movement, _ = consume_stock(
                    batch=batch, quantity=qty,
                    reason="Ward/dispensary issue (bulk demo)",
                    performed_by=performers[fkey],
                )
                StockMovement.objects.filter(pk=movement.pk).update(
                    occurred_at=dt(28 - i * 9)
                )

    # ------------------------------------------------------------------
    # Transfers (driven through the real transfer services so the ledger,
    # reservations and statuses stay exactly like production flows)
    # ------------------------------------------------------------------

    def _seed_transfers(self, products, people, batches):
        coord = people["demo_coord"]
        bole = Facility.objects.get(name="Bole Health Center")
        yeka = Facility.objects.get(name="Yeka Health Center")
        stp = people["stp"]["facility"]
        haw = people["haw"]["facility"]
        jim = people["jim"]["facility"]
        mgr_bole = User.objects.get(username="mgr_bole")
        pharm_bole = User.objects.get(username="pharm_bole")
        mgr_yeka = User.objects.get(username="mgr_yeka")
        mgr_stp = people["stp"]["mgr"]
        pharm_haw = people["haw"]["pharm"]
        mgr_jim = people["jim"]["mgr"]

        def make(source, dest, fkey, pkey, qty, priority, requested_by, notes=""):
            return create_transfer_request(
                source_facility=source,
                destination_facility=dest,
                product=products[pkey],
                source_batch=batches[fkey][pkey],
                quantity_requested=qty,
                priority=priority,
                requested_by=requested_by,
                notes=notes,
            )

        # 1) REQUESTED — Yeka -> Bole paracetamol, awaiting source-side approval
        make(yeka, bole, "yeka", "PARA", 40, TransferRequest.Priority.HIGH,
             requested_by=mgr_bole,
             notes="Dispensary running low; requesting from Yeka surplus.")

        # 2) APPROVED — Yeka -> St. Paul's amoxicillin, reserved, awaiting dispatch
        t2 = make(yeka, stp, "yeka", "AMOX", 30, TransferRequest.Priority.MEDIUM,
                  requested_by=mgr_stp, notes="Surgery reserve depleted.")
        approve_transfer(transfer=t2, approved_by=mgr_yeka, quantity_approved=30)

        # 3) DISPATCHED — Bole -> Yeka BCG, pickup arranged by phone
        t3 = make(bole, yeka, "bole", "BCG", 40, TransferRequest.Priority.CRITICAL,
                  requested_by=mgr_yeka,
                  notes="Yeka BCG stock-out; outreach clinic Monday.")
        approve_transfer(transfer=t3, approved_by=coord, quantity_approved=40)
        dispatch_transfer(transfer=t3, performed_by=pharm_bole,
                          notes="Cold box with gel packs.")
        DeliveryCoordination.objects.create(
            transfer_request=t3, transport_method="pickup",
            transport_provider="Selam Bus Logistics",
            contact_person_name="Yeka pharmacy desk",
            contact_phone="+251911234567",
            transport_payer=DeliveryCoordination.Payer.RECEIVER,
            estimated_cost="180.00", currency="ETB",
            phone_coordination_status=DeliveryCoordination.PhoneStatus.CONFIRMED,
            delivery_status=DeliveryCoordination.DeliveryStatus.ARRANGED_BY_PHONE,
            coordinator=coord, last_contacted_at=dt(0, 10),
            agreed_pickup_at=dt(-1, 14),
            notes="Pickup tomorrow morning; keep at 2-8C.",
        )

        # 4) IN_TRANSIT — Bole -> Hawassa OPV (advanced beyond DISPATCHED)
        t4 = make(bole, haw, "bole", "OPV", 50, TransferRequest.Priority.HIGH,
                  requested_by=people["haw"]["mgr"], notes="Regional top-up.")
        approve_transfer(transfer=t4, approved_by=coord, quantity_approved=50)
        dispatch_transfer(transfer=t4, performed_by=pharm_bole)
        t4.status = TransferRequest.Status.IN_TRANSIT
        t4.save(update_fields=["status", "updated_at"])
        DeliveryCoordination.objects.create(
            transfer_request=t4, transport_method="courier",
            transport_provider="Ethio Cold Chain Couriers",
            contact_person_name="Hawassa vaccine store",
            contact_phone="+251922334455",
            transport_payer=DeliveryCoordination.Payer.CENTRAL,
            estimated_cost="620.00", currency="ETB",
            phone_coordination_status=DeliveryCoordination.PhoneStatus.CONFIRMED,
            delivery_status=DeliveryCoordination.DeliveryStatus.DISPATCHED,
            coordinator=coord, last_contacted_at=dt(0, 8),
            notes="Driver reported departure 08:10; ETA this afternoon.",
        )

        # 5) RECEIVED (with discrepancy) — Hawassa -> Bole cotrimoxazole
        t5 = make(haw, bole, "haw", "COTRI", 100, TransferRequest.Priority.MEDIUM,
                  requested_by=pharm_bole, notes="Bole dispensary replenishment.")
        approve_transfer(transfer=t5, approved_by=coord, quantity_approved=100)
        dispatch_transfer(transfer=t5, performed_by=pharm_haw)
        receive_transfer(transfer=t5, performed_by=pharm_bole,
                         quantity_received=90, condition="OK",
                         notes="10 vials short on arrival; driver noted.")
        DeliveryCoordination.objects.create(
            transfer_request=t5, transport_method="bus-freight",
            transport_provider="Sky Bus Cargo",
            contact_person_name="Bole receiving", contact_phone="+251911000222",
            transport_payer=DeliveryCoordination.Payer.SENDER,
            estimated_cost="240.00", currency="ETB",
            phone_coordination_status=DeliveryCoordination.PhoneStatus.CONFIRMED,
            delivery_status=DeliveryCoordination.DeliveryStatus.RECEIVED,
            coordinator=coord, receipt_confirmed_by=pharm_bole,
            receipt_confirmed_at=dt(1, 16), quantity_received=90,
            condition_on_receipt="OK",
        )

        # 6) REJECTED — St. Paul's -> Yeka measles
        t6 = make(stp, yeka, "stp", "MEASLES", 30, TransferRequest.Priority.MEDIUM,
                  requested_by=mgr_yeka, notes="Campaign buffer request.")
        reject_transfer(transfer=t6, reviewed_by=mgr_stp,
                        rejection_reason=("Measles stock is below our minimum; "
                                          "request again next cycle."))

        # 7) CANCELLED — Jimma -> Bole ibuprofen
        t7 = make(jim, bole, "jim", "IBU", 25, TransferRequest.Priority.LOW,
                  requested_by=mgr_bole, notes="OTC shelf refill.")
        cancel_transfer(transfer=t7, performed_by=mgr_jim,
                        reason="Supplier delivery arrived; internal need only.")

        # 8) FAILED — Bole -> St. Paul's ORS (transport failure after dispatch)
        t8 = make(bole, stp, "bole", "ORS", 60, TransferRequest.Priority.HIGH,
                  requested_by=mgr_stp, notes="Emergency diarrhoea case surge.")
        approve_transfer(transfer=t8, approved_by=coord, quantity_approved=60)
        dispatch_transfer(transfer=t8, performed_by=pharm_bole)
        t8.status = TransferRequest.Status.FAILED
        t8.notes = (t8.notes + "\n" if t8.notes else "") + \
            "Transport breakdown; ORS cartons water-damaged on the road."
        t8.save(update_fields=["status", "notes", "updated_at"])
        DeliveryCoordination.objects.create(
            transfer_request=t8, transport_method="courier",
            transport_provider="Ethio Cold Chain Couriers",
            contact_person_name="St. Paul's receiving",
            contact_phone="+251911555666",
            transport_payer=DeliveryCoordination.Payer.CENTRAL,
            estimated_cost="310.00", currency="ETB",
            phone_coordination_status=DeliveryCoordination.PhoneStatus.CONFIRMED,
            delivery_status=DeliveryCoordination.DeliveryStatus.FAILED,
            coordinator=coord, last_contacted_at=dt(1, 12),
            notes="Vehicle breakdown near Debre Zeit; consignment lost.",
        )

    # ------------------------------------------------------------------
    # Supply gaps
    # ------------------------------------------------------------------

    def _gap(self, facility, product, demand, priority, status, incoming=0,
             assigned=None, reason="", resolution_notes=""):
        usable = self._usable(facility, product)
        uncovered = max(0, demand - usable - incoming)
        return SupplyGapReport.objects.create(
            facility=facility, product=product,
            reporting_horizon_start=date.today(),
            reporting_horizon_end=d(30),
            projected_demand=demand, usable_stock=usable,
            reliable_incoming_quantity=incoming,
            uncovered_quantity=uncovered, priority=priority,
            status=status, assigned_to=assigned,
            reason_summary=reason or
            f"Projected demand {demand} over 30-day horizon; usable stock {usable}.",
            resolution_notes=resolution_notes,
        )

    def _seed_gaps(self, products, people):
        coord = people["demo_coord"]
        bole = Facility.objects.get(name="Bole Health Center")
        yeka = Facility.objects.get(name="Yeka Health Center")
        stp = people["stp"]["facility"]
        haw = people["haw"]["facility"]
        jim = people["jim"]["facility"]

        return {
            "stp_cefi": self._gap(
                stp, products["CEFI"], 160, SupplyGapReport.Priority.CRITICAL,
                SupplyGapReport.Status.OPEN,
                reason="Ceftriaxone usage doubled after meningitis referrals."),
            "stp_opv": self._gap(
                stp, products["OPV"], 140, SupplyGapReport.Priority.HIGH,
                SupplyGapReport.Status.ASSIGNED, assigned=coord,
                reason="Outreach sessions planned; OPV below par level."),
            "haw_penta": self._gap(
                haw, products["PENTA"], 150, SupplyGapReport.Priority.HIGH,
                SupplyGapReport.Status.ACTION_PLANNED,
                reason="Pentavalent buffer exhausted; transfer planned with Bole."),
            "haw_measles": self._gap(
                haw, products["MEASLES"], 120, SupplyGapReport.Priority.MEDIUM,
                SupplyGapReport.Status.UNDER_REVIEW,
                reason="Campaign demand forecast under review."),
            "jim_ors": self._gap(
                jim, products["ORS"], 90, SupplyGapReport.Priority.LOW,
                SupplyGapReport.Status.OPEN,
                reason="Seasonal diarrhoea uptick expected."),
            "bole_metro": self._gap(
                bole, products["METRO"], 130, SupplyGapReport.Priority.CRITICAL,
                SupplyGapReport.Status.ESCALATED, assigned=coord,
                reason="Quarantined batch left Bole below safety stock; escalated to central."),
            "yeka_cotri": self._gap(
                yeka, products["COTRI"], 90, SupplyGapReport.Priority.MEDIUM,
                SupplyGapReport.Status.RESOLVED,
                resolution_notes="Covered by incoming transfer stock; verified on receipt."),
            "bole_ors": self._gap(
                bole, products["ORS"], 110, SupplyGapReport.Priority.LOW,
                SupplyGapReport.Status.CLOSED,
                resolution_notes="Supplier delivery covered the gap; monitoring closed."),
        }

    # ------------------------------------------------------------------
    # Patients + vaccination records + follow-ups
    # ------------------------------------------------------------------

    NAMES = [
        ("Liya Abebe", "Abebe Kebede", "FEMALE"),
        ("Nathan Tesfaye", "Tesfaye Girma", "MALE"),
        ("Sara Solomon", "Solomon Bekele", "FEMALE"),
        ("Yonas Dereje", "Dereje Ayele", "MALE"),
        ("Hanna Mulugeta", "Mulugeta Assefa", "FEMALE"),
        ("Abel Girmay", "Girmay Haile", "MALE"),
        ("Meron Dawit", "Dawit Tessema", "FEMALE"),
        ("Samuel Bereket", "Bereket Paulos", "MALE"),
        ("Rahel Yohannes", "Yohannes Kidane", "FEMALE"),
        ("Kalkidan Fikru", "Fikru Mengistu", "FEMALE"),
        ("Eyob Nahom", "Nahom Zerihun", "MALE"),
        ("Bethlehem Tadesse", "Tadesse Wale", "FEMALE"),
        ("Mikias Tewodros", "Tewodros Kassa", "MALE"),
        ("Selam Girma", "Girma Wolde", "FEMALE"),
        ("Dawit Alemayehu", "Alemayehu Genet", "MALE"),
        ("Mahlet Biniam", "Biniam Negash", "FEMALE"),
    ]

    AGE_BUCKETS = (25, 45, 60, 120, 180, 210, 260, 300, 330, 400)

    def _patients(self, facility, prefix, count, start, creator):
        rows = []
        for i in range(count):
            name, guardian, sex = self.NAMES[(start + i) % len(self.NAMES)]
            dob_days = self.AGE_BUCKETS[(start + i) % len(self.AGE_BUCKETS)]
            consent = (i % 7 != 3)
            rows.append(Patient.objects.create(
                facility=facility,
                patient_number=f"DEMO-{prefix}-{start + i:03d}",
                full_name=name,
                date_of_birth=d(-dob_days),
                sex=sex,
                guardian_name=guardian,
                guardian_phone=f"+25191{start + i:06d}",
                address_area=facility.town or facility.region,
                consent_given=consent,
                consent_date=d(-1) if consent else None,
                created_by=creator,
            ))
        return rows

    def _doses_for_age(self, dob_days):
        """(product_key, dose, days_ago) list for a patient of the given age."""
        doses = [("BCG", 1, dob_days)]
        if dob_days > 45:
            for key in ("OPV", "PENTA", "PCV", "ROTA"):
                doses.append((key, 1, dob_days - 42))
        if dob_days > 73:
            for key in ("OPV", "PENTA", "PCV", "ROTA"):
                doses.append((key, 2, dob_days - 70))
        if dob_days > 101:
            for key in ("OPV", "PENTA", "PCV"):
                doses.append((key, 3, dob_days - 98))
        if dob_days > 273:
            doses.append(("MEASLES", 1, dob_days - 270))
        return [(k, dose, days) for k, dose, days in doses if days > 0]

    def _seed_patients_and_vaccinations(self, products, people, batches):
        plan = {
            "bole": ("BOLE", 8, 4, Facility.objects.get(name="Bole Health Center"),
                     [User.objects.get(username="hw_bole")]),
            "yeka": ("YEK", 5, 6, Facility.objects.get(name="Yeka Health Center"),
                     [people["hw_yeka"]]),
            "stp": ("STP", 12, 1, people["stp"]["facility"],
                    [people["stp"]["hw"], people["stp"]["hw2"]]),
            "haw": ("HAW", 8, 1, people["haw"]["facility"], [people["haw"]["hw"]]),
        }

        for fkey, (prefix, count, start, facility, hws) in plan.items():
            patients = self._patients(facility, prefix, count, start, hws[0])
            for idx, patient in enumerate(patients):
                dob_days = (date.today() - patient.date_of_birth).days
                hw = hws[idx % len(hws)]
                for pkey, dose, days_ago in self._doses_for_age(dob_days):
                    record_vaccination(
                        patient=patient,
                        vaccine_product=products[pkey],
                        dose_number=dose,
                        administered_at=dt(days_ago, hour=10 + idx % 5),
                        facility=facility,
                        batch=batches[fkey][pkey],
                        recorded_by=hw,
                        notes="Bulk demo record",
                    )

            # Follow-up variety: nudge some auto-created follow-ups into each state.
            hw = hws[0]
            follow_ups = list(
                VaccineFollowUp.objects.filter(patient__facility=facility)
                .order_by("due_date", "id")
            )
            upcoming = [f for f in follow_ups if f.status == VaccineFollowUp.Status.UPCOMING]
            for f in upcoming[:4]:
                VaccineFollowUp.objects.filter(pk=f.pk).update(
                    due_date=d(-6), status=VaccineFollowUp.Status.OVERDUE
                )
            for f in upcoming[4:6]:
                VaccineFollowUp.objects.filter(pk=f.pk).update(
                    due_date=date.today(), status=VaccineFollowUp.Status.DUE
                )
            refreshed = list(
                VaccineFollowUp.objects.filter(patient__facility=facility)
                .exclude(status__in=[VaccineFollowUp.Status.COMPLETED,
                                     VaccineFollowUp.Status.CANCELLED])
                .order_by("due_date", "id")
            )
            if refreshed:
                record_contact(
                    follow_up=refreshed[0],
                    outcome=VaccineFollowUp.ContactOutcome.NO_ANSWER,
                    performed_by=hw, notes="Called twice, no answer.",
                )
            if len(refreshed) > 1:
                record_contact(
                    follow_up=refreshed[1],
                    outcome=VaccineFollowUp.ContactOutcome.RESCHEDULED,
                    next_action_date=d(7), performed_by=hw,
                    notes="Guardian asked to come next week.",
                )
            if len(refreshed) > 2:
                mark_review_required(
                    follow_up=refreshed[2], performed_by=hw,
                    reason="Guardian phone unreachable; address needs verification.",
                )
            if len(refreshed) > 3:
                cancel_follow_up(
                    follow_up=refreshed[3], performed_by=hw,
                    reason="Family relocated out of catchment area.",
                )
            if len(refreshed) > 4:
                VaccineFollowUp.objects.filter(pk=refreshed[4].pk).update(assigned_to=hw)

    # ------------------------------------------------------------------
    # Equipment
    # ------------------------------------------------------------------

    def _seed_equipment(self, people):
        stp = people["stp"]["facility"]
        haw = people["haw"]["facility"]
        jim = people["jim"]["facility"]
        rows = [
            (stp, "Refrigerator", "cold-chain", "SPP-FR-01", 2,
             Equipment.Condition.OPERATIONAL, "Ward A"),
            (stp, "Refrigerator", "cold-chain", "SPP-FR-02", 1,
             Equipment.Condition.NEEDS_MAINTENANCE, "Compressor noisy"),
            (stp, "Cold box", "cold-chain", "SPP-CB-01", 4,
             Equipment.Condition.OPERATIONAL, ""),
            (stp, "Vaccine carrier", "cold-chain", "SPP-VC-01", 6,
             Equipment.Condition.OPERATIONAL, ""),
            (stp, "Weighing scale", "general", "SPP-SC-01", 2,
             Equipment.Condition.OPERATIONAL, ""),
            (haw, "Refrigerator", "cold-chain", "HAW-FR-01", 2,
             Equipment.Condition.OPERATIONAL, ""),
            (haw, "Freezer", "cold-chain", "HAW-FRZ-01", 1,
             Equipment.Condition.OUT_OF_SERVICE, "Awaiting spare parts"),
            (haw, "Cold box", "cold-chain", "HAW-CB-01", 3,
             Equipment.Condition.OPERATIONAL, ""),
            (jim, "Refrigerator", "cold-chain", "JIM-FR-01", 1,
             Equipment.Condition.NEEDS_MAINTENANCE, "Door seal worn"),
        ]
        for facility, name, category, asset, qty, condition, notes in rows:
            Equipment.objects.create(
                facility=facility, name=name, category=category,
                asset_identifier=asset, quantity=qty, condition=condition,
                notes=notes, last_checked_at=timezone.now() - timedelta(days=2),
                created_by=people["demo_admin"],
            )

    # ------------------------------------------------------------------
    # AI recommendations
    # ------------------------------------------------------------------

    def _seed_ai(self, products, people, gaps):
        coord = people["demo_coord"]
        bole = Facility.objects.get(name="Bole Health Center")
        yeka = Facility.objects.get(name="Yeka Health Center")
        haw = people["haw"]["facility"]
        mgr_bole = User.objects.get(username="mgr_bole")
        mgr_yeka = User.objects.get(username="mgr_yeka")

        AIRecommendation.objects.create(
            analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
            status=AIRecommendation.Status.PENDING_REVIEW,
            scope_facility=bole, requested_by=mgr_bole,
            model_name="gemini-2.5-flash",
            summary=(
                "Bole Health Center holds healthy paracetamol and ORS stock, but the "
                "Measles batch expires within ~5 weeks while demand remains steady, and "
                "one Amoxicillin batch is already expired. Recommend redistributing "
                "near-expiry measles doses to high-uptake sites and disposing of the "
                "expired Amoxicillin remainder."
            ),
            input_snapshot={"horizon_days": 30, "usage_window_days": 30,
                            "facility_id": bole.id, "seed": "bulk_demo_v1"},
            raw_output={},
            validated_output={
                "risks": [
                    {"facility_id": bole.id, "product_id": products["MEASLES"].id,
                     "priority": "CRITICAL",
                     "reason": "Near-expiry measles stock (~150 doses) against steady outreach demand."},
                    {"facility_id": bole.id, "product_id": products["AMOX"].id,
                     "priority": "HIGH",
                     "reason": "Expired Amoxicillin batch still occupying cold-room space; disposal pending."},
                    {"facility_id": bole.id, "product_id": products["METRO"].id,
                     "priority": "HIGH",
                     "reason": "Quarantined batch plus escalated gap leaves Metronidazole below safety stock."},
                ],
                "transfer_recommendations": [
                    {"source_facility_id": bole.id, "destination_facility_id": yeka.id,
                     "product_id": products["MEASLES"].id, "quantity": 40,
                     "reason": "Yeka has no measles stock; Bole batch expires soonest."},
                ],
                "unresolved_gaps": [
                    {"facility_id": bole.id, "product_id": products["METRO"].id,
                     "quantity": gaps["bole_metro"].uncovered_quantity},
                ],
                "missing_information": [
                    "Scheduled outreach session counts for the next 30 days."
                ],
            },
        )
        AIRecommendation.objects.create(
            analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
            status=AIRecommendation.Status.PENDING_REVIEW,
            scope_facility=people["stp"]["facility"],
            requested_by=people["stp"]["mgr"],
            model_name="gemini-2.5-flash",
            summary=(
                "St. Paul's overall position is stable; Ceftriaxone is the binding "
                "constraint with an open critical gap, and OPV must cover planned "
                "outreach sessions. No expired stock detected."
            ),
            input_snapshot={"horizon_days": 30, "usage_window_days": 30,
                            "facility_id": people["stp"]["facility"].id,
                            "seed": "bulk_demo_v1"},
            validated_output={
                "risks": [
                    {"facility_id": people["stp"]["facility"].id,
                     "product_id": products["CEFI"].id, "priority": "CRITICAL",
                     "reason": "Open critical gap; 30-day demand roughly double usable stock."},
                    {"facility_id": people["stp"]["facility"].id,
                     "product_id": products["OPV"].id, "priority": "HIGH",
                     "reason": "Assigned gap; outreach sessions will consume the remainder."},
                ],
                "transfer_recommendations": [],
                "unresolved_gaps": [
                    {"facility_id": people["stp"]["facility"].id,
                     "product_id": products["CEFI"].id,
                     "quantity": gaps["stp_cefi"].uncovered_quantity},
                    {"facility_id": people["stp"]["facility"].id,
                     "product_id": products["OPV"].id,
                     "quantity": gaps["stp_opv"].uncovered_quantity},
                ],
                "missing_information": [],
            },
        )
        AIRecommendation.objects.create(
            analysis_type=AIRecommendation.AnalysisType.SUPPLY_GAP_PRIORITIZATION,
            status=AIRecommendation.Status.PENDING_REVIEW,
            scope_facility=None, requested_by=coord,
            model_name="gemini-2.5-flash",
            summary=(
                "Six open gaps nationwide. Escalated Metronidazole at Bole and the "
                "critical Ceftriaxone gap at St. Paul's should be actioned first; the "
                "Jimma ORS gap is low urgency and can wait for seasonal stock."
            ),
            input_snapshot={"open_gaps": 6, "seed": "bulk_demo_v1"},
            validated_output={
                "ranked_gaps": [
                    {"gap_id": gaps["bole_metro"].id, "priority": "CRITICAL", "rank": 1,
                     "reason": "Escalated with quarantined stock; safety stock breached."},
                    {"gap_id": gaps["stp_cefi"].id, "priority": "CRITICAL", "rank": 2,
                     "reason": "Demand roughly double usable stock at a referral hospital."},
                    {"gap_id": gaps["haw_penta"].id, "priority": "HIGH", "rank": 3,
                     "reason": "Action planned; coordinate with Bole surplus transfer."},
                    {"gap_id": gaps["stp_opv"].id, "priority": "HIGH", "rank": 4,
                     "reason": "Outreach sessions will exhaust OPV within the horizon."},
                    {"gap_id": gaps["haw_measles"].id, "priority": "MEDIUM", "rank": 5,
                     "reason": "Forecast under review; no immediate stock-out."},
                    {"gap_id": gaps["jim_ors"].id, "priority": "LOW", "rank": 6,
                     "reason": "Seasonal; low uncovered quantity."},
                ],
                "missing_information": [],
            },
        )
        AIRecommendation.objects.create(
            analysis_type=AIRecommendation.AnalysisType.SUPPLY_GAP_PRIORITIZATION,
            status=AIRecommendation.Status.APPROVED,
            scope_facility=None, requested_by=coord,
            model_name="gemini-2.5-flash",
            summary=(
                "Earlier weekly triage: transfer-parcel coordination resolved the "
                "Yeka cotrimoxazole gap; remaining gaps forwarded to assigned owners."
            ),
            input_snapshot={"open_gaps": 3, "seed": "bulk_demo_v1"},
            validated_output={
                "ranked_gaps": [
                    {"gap_id": gaps["yeka_cotri"].id, "priority": "MEDIUM", "rank": 1,
                     "reason": "Resolved by incoming transfer; verify on receipt."},
                ],
                "missing_information": [],
            },
            reviewed_by=coord, reviewed_at=dt(2, 15),
            review_note="Agreed with ranking; owners notified by phone.",
        )
        AIRecommendation.objects.create(
            analysis_type=AIRecommendation.AnalysisType.VACCINATION_DEMAND_SUMMARY,
            status=AIRecommendation.Status.PENDING_REVIEW,
            scope_facility=haw, requested_by=people["haw"]["hw"],
            model_name="gemini-2.5-flash",
            summary=(
                "Demand at Hawassa is concentrated in pentavalent and OPV follow-ups; "
                "open follow-ups fall due across the next 30 days while usable stock "
                "covers most but not all projected doses. Priorities: confirm the "
                "inbound OPV transfer, reschedule unreachable guardians, and top up "
                "pentavalent."
            ),
            input_snapshot={"horizon_days": 30, "facility_id": haw.id,
                            "seed": "bulk_demo_v1"},
            validated_output={
                "by_product": [
                    {"product_id": products["PENTA"].id,
                     "product_name": products["PENTA"].name,
                     "open_follow_ups": 6, "due_next_7_days": 2, "due_next_30_days": 6,
                     "usable_stock": self._usable(haw, products["PENTA"]),
                     "projected_gap": 18,
                     "comment": "Third doses dominate the 30-day queue."},
                    {"product_id": products["OPV"].id,
                     "product_name": products["OPV"].name,
                     "open_follow_ups": 6, "due_next_7_days": 2, "due_next_30_days": 5,
                     "usable_stock": self._usable(haw, products["OPV"]),
                     "projected_gap": 10,
                     "comment": "In-transit transfer covers most of the gap."},
                    {"product_id": products["BCG"].id,
                     "product_name": products["BCG"].name,
                     "open_follow_ups": 4, "due_next_7_days": 1, "due_next_30_days": 4,
                     "usable_stock": self._usable(haw, products["BCG"]),
                     "projected_gap": None,
                     "comment": "Birth-dose pipeline steady."},
                ],
                "priorities": [
                    "Confirm OPV transfer arrival before Monday outreach",
                    "Call the two overdue pentavalent guardians",
                    "Request small pentavalent top-up via supply gap",
                ],
                "missing_information": [],
            },
        )
        AIRecommendation.objects.create(
            analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
            status=AIRecommendation.Status.FAILED,
            scope_facility=yeka, requested_by=mgr_yeka,
            model_name="gemini-2.5-flash",
            summary="",
            input_snapshot={"horizon_days": 30, "facility_id": yeka.id,
                            "seed": "bulk_demo_v1"},
            error="Gemini API timeout after 2 retries (demo failure record).",
        )
