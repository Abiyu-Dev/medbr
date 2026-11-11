from datetime import date, datetime, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AuditLog, User
from facilities.models import Facility
from inventory.models import Product, StockBatch
from inventory.services import receive_stock
from vaccinations.models import Patient, VaccinationRecord, VaccineFollowUp, VaccineSchedule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mk_user(username, role, facility=None, password="TestPass123!"):
    return User.objects.create_user(
        username=username,
        password=password,
        email=f"{username}@x.com",
        role=role,
        facility=facility,
    )


def _mk_facility(
    name="F", provides_vaccination_services=True, has_cold_chain=True
):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=Facility.Status.APPROVED,
        provides_vaccination_services=provides_vaccination_services,
        has_cold_chain=has_cold_chain,
    )


def _mk_vaccine(name="BCG"):
    return Product.objects.create(
        name=name,
        category=Product.Category.VACCINE,
        requires_cold_chain=False,  # avoid cold-chain gate in tests
        unit_of_measure="dose",
    )


def _mk_medicine(name="Paracetamol"):
    return Product.objects.create(name=name, category=Product.Category.MEDICINE)


def _mk_patient(facility, dob=None, user=None, **over):
    data = {
        "facility": facility,
        "patient_number": over.pop("patient_number", "P-0001"),
        "full_name": over.pop("full_name", "Test Patient"),
        "date_of_birth": dob or (date.today() - timedelta(days=365)),
    }
    data.update(over)
    return Patient.objects.create(created_by=user, **data)


def _mk_batch(facility, product, user, qty=100, expiry_days=180, batch_number=None):
    batch, _, _ = receive_stock(          # ✅ batch ← batch
        facility=facility,
        product=product,
        batch_number=batch_number or f"B-{product.id}-{facility.id}",
        expiry_date=date.today() + timedelta(days=expiry_days),
        quantity=qty,
        performed_by=user,
    )
    return batch


def _mk_schedule(vaccine, dose_number, interval=None, age=None, active=True):
    return VaccineSchedule.objects.create(
        vaccine_product=vaccine,
        dose_number=dose_number,
        recommended_age_days=age,
        minimum_interval_days=interval,
        effective_from=date.today() - timedelta(days=30),
        source_name="Ethiopia EPI",
        source_version="2024.1",
        active=active,
    )


# ---------------------------------------------------------------------------
# Patient tests
# ---------------------------------------------------------------------------


class PatientApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Home")
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fac)
        self.other_fac = _mk_facility("Other")
        self.other_hw = _mk_user("hwo", User.Role.HEALTH_WORKER, facility=self.other_fac)

    def _payload(self, **over):
        data = {
            "full_name": "Jane Doe",
            "date_of_birth": str(date.today() - timedelta(days=100)),
            "sex": "FEMALE",
            "patient_phone": "+251911000000",
        }
        data.update(over)
        return data

    def test_health_worker_creates_patient_with_auto_number(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post("/api/v1/patients/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.data["patient_number"].startswith("P-"))
        self.assertEqual(r.data["facility"], self.fac.id)

    def test_explicit_patient_number_used(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/patients/",
            self._payload(patient_number="CUSTOM-001"),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["patient_number"], "CUSTOM-001")

    def test_duplicate_patient_number_rejected(self):
        _mk_patient(self.fac, patient_number="DUP-1")
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/patients/", self._payload(patient_number="DUP-1"), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_future_dob_rejected(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/patients/",
            self._payload(date_of_birth=str(date.today() + timedelta(days=1))),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pharmacist_cannot_create(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post("/api/v1/patients/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_health_worker_at_non_vaccination_facility_blocked(self):
        no_vax = _mk_facility("NoVax", provides_vaccination_services=False)
        hw2 = _mk_user("hw2", User.Role.HEALTH_WORKER, facility=no_vax)
        self.client.force_authenticate(hw2)
        r = self.client.post("/api/v1/patients/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_facility_access_blocked(self):
        p = _mk_patient(self.other_fac, patient_number="OTHER-1")
        self.client.force_authenticate(self.hw)
        r = self.client.get(f"/api/v1/patients/{p.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_only_own_facility(self):
        _mk_patient(self.fac, patient_number="HOME-1")
        _mk_patient(self.other_fac, patient_number="OTHER-1")
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/patients/")
        self.assertEqual(r.data["count"], 1)

    def test_patch_patient(self):
        p = _mk_patient(self.fac)
        self.client.force_authenticate(self.hw)
        r = self.client.patch(
            f"/api/v1/patients/{p.id}/",
            {"patient_phone": "+251911111111"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        p.refresh_from_db()
        self.assertEqual(p.patient_phone, "+251911111111")


# ---------------------------------------------------------------------------
# Vaccine schedule tests
# ---------------------------------------------------------------------------


class VaccineScheduleApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.fac = _mk_facility("Home")
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.vaccine = _mk_vaccine()
        self.medicine = _mk_medicine()

    def _payload(self, **over):
        data = {
            "vaccine_product": self.vaccine.id,
            "dose_number": 1,
            "recommended_age_days": 0,
            "recommended_age_label": "at birth",
            "effective_from": str(date.today()),
            "source_name": "Ethiopia EPI",
            "source_version": "2024.1",
            "active": True,
        }
        data.update(over)
        return data

    def test_admin_creates_schedule(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/vaccination-schedules/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["dose_number"], 1)
        self.assertEqual(r.data["approved_by"], self.admin.id)

    def test_coordinator_can_create(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            "/api/v1/vaccination-schedules/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_health_worker_cannot_create(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-schedules/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_health_worker_can_list(self):
        _mk_schedule(self.vaccine, 1, age=0)
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/vaccination-schedules/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 1)

    def test_non_vaccine_product_rejected(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/vaccination-schedules/",
            self._payload(vaccine_product=self.medicine.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_age_and_no_interval_rejected(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/vaccination-schedules/",
            self._payload(recommended_age_days=None),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_version_supersedes_old(self):
        self.client.force_authenticate(self.admin)
        r1 = self.client.post(
            "/api/v1/vaccination-schedules/", self._payload(), format="json"
        )
        r2 = self.client.post(
            "/api/v1/vaccination-schedules/",
            self._payload(source_version="2025.1"),
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        old = VaccineSchedule.objects.get(id=r1.data["id"])
        self.assertFalse(old.active)


# ---------------------------------------------------------------------------
# Vaccination record tests
# ---------------------------------------------------------------------------


class VaccinationRecordApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Home")
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.other_fac = _mk_facility("Other")
        self.other_hw = _mk_user("hwo", User.Role.HEALTH_WORKER, facility=self.other_fac)
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fac)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)

        self.vaccine = _mk_vaccine()
        _mk_schedule(self.vaccine, 1, age=0)
        _mk_schedule(self.vaccine, 2, interval=28)

        self.patient = _mk_patient(self.fac, patient_number="P-001")
        self.batch = _mk_batch(self.fac, self.vaccine, self.hw, qty=50)

    def _payload(self, **over):
        data = {
            "patient": self.patient.id,
            "vaccine_product": self.vaccine.id,
            "dose_number": 1,
            "administered_at": timezone.now().isoformat(),
            "batch": self.batch.id,
        }
        data.update(over)
        return data

    def test_records_dose_and_creates_movement(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-records/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["record"]["dose_number"], 1)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 49)
        from inventory.models import StockMovement

        mv = StockMovement.objects.filter(
            movement_type="VACCINATION_ADMINISTRATION"
        ).first()
        self.assertIsNotNone(mv)
        self.assertEqual(mv.quantity, 1)

    def test_creates_next_dose_follow_up(self):
        from datetime import datetime as _dt

        self.client.force_authenticate(self.hw)

        # Pin a timestamp *in the past* so it never trips the "cannot be in the
        # future" guard regardless of when this test runs. Derive the expected
        # due date from the server's persisted value so any timezone round-trip
        # is identical on both sides.
        fixed_at = timezone.now() - timedelta(minutes=5)
        payload = {**self._payload(), "administered_at": fixed_at.isoformat()}

        r = self.client.post(
            "/api/v1/vaccination-records/", payload, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(r.data["next_follow_up"])
        self.assertEqual(r.data["next_follow_up"]["dose_number"], 2)

        returned_administered = _dt.fromisoformat(
            r.data["record"]["administered_at"]
        )
        expected_due = returned_administered.date() + timedelta(days=28)

        self.assertEqual(
            r.data["next_follow_up"]["due_date"], str(expected_due)
        )

    def test_completes_matching_follow_up(self):
        # Pre-create a follow-up for dose 1
        fu = VaccineFollowUp.objects.create(
            patient=self.patient,
            vaccine_product=self.vaccine,
            dose_number=1,
            due_date=date.today(),
            status=VaccineFollowUp.Status.OVERDUE,
        )
        self.client.force_authenticate(self.hw)
        self.client.post("/api/v1/vaccination-records/", self._payload(), format="json")
        fu.refresh_from_db()
        self.assertEqual(fu.status, VaccineFollowUp.Status.COMPLETED)

    def test_duplicate_dose_rejected(self):
        self.client.force_authenticate(self.hw)
        self.client.post("/api/v1/vaccination-records/", self._payload(), format="json")
        r = self.client.post(
            "/api/v1/vaccination-records/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already recorded", str(r.data).lower())

    def test_dose_2_requires_dose_1(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-records/",
            self._payload(dose_number=2),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_product_batch_rejected(self):
        other_vaccine = _mk_vaccine("Measles")
        _mk_schedule(other_vaccine, 1, age=270)
        other_batch = _mk_batch(self.fac, other_vaccine, self.hw)
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-records/",
            self._payload(batch=other_batch.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_facility_batch_rejected(self):
        other_batch = _mk_batch(self.other_fac, self.vaccine, self.other_hw)
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-records/",
            self._payload(batch=other_batch.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_facility_patient_rejected(self):
        other_patient = _mk_patient(self.other_fac, patient_number="OP-1")
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-records/",
            self._payload(patient=other_patient.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pharmacist_cannot_record(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/vaccination-records/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_health_worker_at_non_vax_facility_blocked(self):
        no_vax = _mk_facility("NoVax", provides_vaccination_services=False)
        hw2 = _mk_user("hw2", User.Role.HEALTH_WORKER, facility=no_vax)
        self.client.force_authenticate(hw2)
        r = self.client.post(
            "/api/v1/vaccination-records/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Follow-up tests
# ---------------------------------------------------------------------------


class FollowUpApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Home")
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.vaccine = _mk_vaccine()
        _mk_schedule(self.vaccine, 1, age=0)
        _mk_schedule(self.vaccine, 2, interval=28)
        self.patient = _mk_patient(self.fac, patient_number="P-001")

    def _mk_fu(self, dose=1, status="UPCOMING", due=None, **over):
        return VaccineFollowUp.objects.create(
            patient=self.patient,
            vaccine_product=self.vaccine,
            dose_number=dose,
            due_date=due or (date.today() + timedelta(days=7)),
            status=status,
            **over,
        )

    def test_manual_create_requires_active_schedule(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-followups/",
            {
                "patient": self.patient.id,
                "vaccine_product": self.vaccine.id,
                "dose_number": 3,  # no schedule
                "due_date": str(date.today() + timedelta(days=30)),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manual_create_ok(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-followups/",
            {
                "patient": self.patient.id,
                "vaccine_product": self.vaccine.id,
                "dose_number": 1,
                "due_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "UPCOMING")

    def test_duplicate_open_followup_rejected(self):
        self._mk_fu()
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            "/api/v1/vaccination-followups/",
            {
                "patient": self.patient.id,
                "vaccine_product": self.vaccine.id,
                "dose_number": 1,
                "due_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contact_reached_sets_attempted(self):
        fu = self._mk_fu()
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/contact/",
            {"outcome": "REACHED", "notes": "Patient said will come"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        fu.refresh_from_db()
        self.assertEqual(fu.status, VaccineFollowUp.Status.CONTACT_ATTEMPTED)
        self.assertEqual(fu.contact_outcome, "REACHED")
        self.assertIsNotNone(fu.last_contacted_at)

    def test_contact_rescheduled_updates_due_date(self):
        fu = self._mk_fu()
        new_date = date.today() + timedelta(days=10)
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/contact/",
            {
                "outcome": "RESCHEDULED",
                "next_action_date": str(new_date),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        fu.refresh_from_db()
        self.assertEqual(fu.due_date, new_date)
        self.assertEqual(fu.next_action_date, new_date)

    def test_contact_rescheduled_without_date_rejected(self):
        fu = self._mk_fu()
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/contact/",
            {"outcome": "RESCHEDULED"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contact_referred_sets_review_required(self):
        fu = self._mk_fu()
        self.client.force_authenticate(self.hw)
        self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/contact/",
            {"outcome": "REFERRED_FOR_REVIEW"},
            format="json",
        )
        fu.refresh_from_db()
        self.assertEqual(fu.status, VaccineFollowUp.Status.REVIEW_REQUIRED)

    def test_mark_review_required(self):
        fu = self._mk_fu()
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/mark-review-required/",
            {"reason": "Complex catch-up case"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        fu.refresh_from_db()
        self.assertEqual(fu.status, VaccineFollowUp.Status.REVIEW_REQUIRED)

    def test_cancel(self):
        fu = self._mk_fu()
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/cancel/",
            {"reason": "Patient moved"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        fu.refresh_from_db()
        self.assertEqual(fu.status, VaccineFollowUp.Status.CANCELLED)

    def test_cannot_contact_completed(self):
        fu = self._mk_fu(status="COMPLETED")
        self.client.force_authenticate(self.hw)
        r = self.client.post(
            f"/api/v1/vaccination-followups/{fu.id}/contact/",
            {"outcome": "REACHED"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Due / Overdue endpoints
# ---------------------------------------------------------------------------


class DueOverdueApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Home")
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.other_fac = _mk_facility("Other")
        self.other_hw = _mk_user("hwo", User.Role.HEALTH_WORKER, facility=self.other_fac)
        self.vaccine = _mk_vaccine()
        _mk_schedule(self.vaccine, 1, age=0)
        _mk_schedule(self.vaccine, 2, interval=28)
        self.p1 = _mk_patient(self.fac, patient_number="A")
        self.p2 = _mk_patient(self.fac, patient_number="B")
        self.p_other = _mk_patient(self.other_fac, patient_number="C")

    def _mk_fu(self, patient, due, status="UPCOMING"):
        return VaccineFollowUp.objects.create(
            patient=patient,
            vaccine_product=self.vaccine,
            dose_number=1,
            due_date=due,
            status=status,
        )

    def test_due_includes_window(self):
        today = date.today()
        self._mk_fu(self.p1, today)
        self._mk_fu(self.p2, today + timedelta(days=5))
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/vaccinations/due/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 2)

    def test_due_excludes_far_future(self):
        self._mk_fu(self.p1, date.today() + timedelta(days=30))
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/vaccinations/due/")
        self.assertEqual(r.data["count"], 0)

    def test_overdue(self):
        self._mk_fu(self.p1, date.today() - timedelta(days=3))
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/vaccinations/overdue/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 1)

    def test_overdue_excludes_completed(self):
        self._mk_fu(self.p1, date.today() - timedelta(days=3), status="COMPLETED")
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/vaccinations/overdue/")
        self.assertEqual(r.data["count"], 0)

    def test_facility_scoping(self):
        self._mk_fu(self.p1, date.today() - timedelta(days=3))
        self._mk_fu(self.p_other, date.today() - timedelta(days=3))
        self.client.force_authenticate(self.hw)
        r = self.client.get("/api/v1/vaccinations/overdue/")
        self.assertEqual(r.data["count"], 1)

    def test_lazy_status_sync(self):
        # Stored UPCOMING but due_date is in the past → sync sets OVERDUE
        fu = self._mk_fu(self.p1, date.today() - timedelta(days=2), status="UPCOMING")
        self.client.force_authenticate(self.hw)
        self.client.get("/api/v1/vaccinations/overdue/")
        fu.refresh_from_db()
        self.assertEqual(fu.status, VaccineFollowUp.Status.OVERDUE)


# ---------------------------------------------------------------------------
# Demand integration
# ---------------------------------------------------------------------------


class FollowUpDemandIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Home")
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.vaccine = _mk_vaccine()
        _mk_schedule(self.vaccine, 1, age=0)
        _mk_schedule(self.vaccine, 2, interval=28)
        # Two patients with upcoming follow-ups
        self.p1 = _mk_patient(self.fac, patient_number="A")
        self.p2 = _mk_patient(self.fac, patient_number="B")
        VaccineFollowUp.objects.create(
            patient=self.p1,
            vaccine_product=self.vaccine,
            dose_number=1,
            due_date=date.today() + timedelta(days=5),
        )
        VaccineFollowUp.objects.create(
            patient=self.p2,
            vaccine_product=self.vaccine,
            dose_number=1,
            due_date=date.today() + timedelta(days=10),
        )

    def test_follow_up_demand_appears_in_summary(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(
            f"/api/v1/inventory/summary/?facility={self.fac.id}&horizon_days=30"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        row = next(
            (it for it in r.data["items"] if it["product_id"] == self.vaccine.id), None
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["follow_up_demand"], 2)
        self.assertEqual(row["projected_demand"], 2)  # max(0, 2)

    def test_completed_follow_up_not_counted(self):
        VaccineFollowUp.objects.filter(patient=self.p1).update(status="COMPLETED")
        self.client.force_authenticate(self.admin)
        r = self.client.get(
            f"/api/v1/inventory/summary/?facility={self.fac.id}&horizon_days=30"
        )
        row = next(
            (it for it in r.data["items"] if it["product_id"] == self.vaccine.id), None
        )
        self.assertEqual(row["follow_up_demand"], 1)

    def test_far_future_follow_up_not_in_horizon(self):
        VaccineFollowUp.objects.filter(patient=self.p2).update(
            due_date=date.today() + timedelta(days=90)
        )
        self.client.force_authenticate(self.admin)
        r = self.client.get(
            f"/api/v1/inventory/summary/?facility={self.fac.id}&horizon_days=30"
        )
        row = next(
            (it for it in r.data["items"] if it["product_id"] == self.vaccine.id), None
        )
        self.assertEqual(row["follow_up_demand"], 1)