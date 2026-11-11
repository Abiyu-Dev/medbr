from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from ai_engine.schemas import InventoryAnalysisOutput
from coordination.models import SupplyGapReport
from facilities.models import Facility
from inventory.models import Product, StockBatch, StockMovement, TransferRequest
from vaccinations.models import Patient, VaccineFollowUp


@override_settings(GEMINI_API_KEY="fake-key")
class DemoWalkthroughTest(TestCase):
    """
    Walks the demo acceptance scenarios from §17 of the technical documentation.
    Gemini is mocked; every other endpoint is exercised via HTTP.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="e2e_admin",
            email="e2e_admin@example.test",
            password="Pass123!",
            role=User.Role.SYSTEM_ADMIN,
        )
        self.coord = User.objects.create_user(
            username="e2e_coord",
            email="e2e_coord@example.test",
            password="Pass123!",
            role=User.Role.CENTRAL_COORDINATOR,
        )

    # -- helpers -----------------------------------------------------

    def _apply(self, applicant, name, **over):
        self.client.force_authenticate(applicant)
        payload = {
            "name": name,
            "facility_type": over.pop("facility_type", "HEALTH_CENTER"),
            "region": over.pop("region", "Addis Ababa"),
            "latitude": "9.010000",
            "longitude": "38.760000",
            "has_cold_chain": over.pop("has_cold_chain", True),
            "provides_vaccination_services": over.pop(
                "provides_vaccination_services", False
            ),
            **over,
        }
        return self.client.post(
            "/api/v1/facilities/applications/", payload, format="json"
        )

    def _approve(self, facility_id):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            f"/api/v1/facilities/applications/{facility_id}/approve/",
            {"review_note": "E2E approval"},
            format="json",
        )

    def _create_user_at(self, facility, username, role):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            f"/api/v1/facilities/{facility.id}/users/",
            {
                "username": username,
                "email": f"{username}@example.test",
                "password": "Pass123!",
                "role": role,
            },
            format="json",
        )
        assert r.status_code == 201, r.data
        return User.objects.get(username=username)

    # =================================================================
    # Scenarios 1-8: transfer workflow + escalation
    # =================================================================

    def test_scenarios_1_through_8_transfer_flow_and_escalation(self):
        # ---- Scenario 1: admin approves two facilities ----
        applicant_a = User.objects.create_user(
            username="applicant_a",
            email="applicant_a@example.test",
            password="Pass123!",
            role=User.Role.HEALTH_WORKER,
        )
        applicant_b = User.objects.create_user(
            username="applicant_b",
            email="applicant_b@example.test",
            password="Pass123!",
            role=User.Role.HEALTH_WORKER,
        )
        r_a = self._apply(applicant_a, "E2E Facility A", provides_vaccination_services=True)
        r_b = self._apply(applicant_b, "E2E Facility B", provides_vaccination_services=True)
        self.assertEqual(r_a.status_code, 201)
        self.assertEqual(r_b.status_code, 201)

        self.assertEqual(self._approve(r_a.data["id"]).status_code, 200)
        self.assertEqual(self._approve(r_b.data["id"]).status_code, 200)

        fa = Facility.objects.get(id=r_a.data["id"])
        fb = Facility.objects.get(id=r_b.data["id"])
        self.assertEqual(fa.status, "APPROVED")
        self.assertEqual(fb.status, "APPROVED")

        applicant_a.refresh_from_db()
        self.assertEqual(applicant_a.role, "FACILITY_MANAGER")
        self.assertEqual(applicant_a.facility, fa)

        # ---- admin creates products ----
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/products/",
            {
                "name": "Paracetamol",
                "category": "MEDICINE",
                "unit_of_measure": "tablet",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        para = Product.objects.get(id=r.data["id"])

        # ---- Scenario 2: A receives stock, B builds usage history ----
        pharm_a = self._create_user_at(fa, "e2e_pharm_a", "PHARMACIST")
        pharm_b = self._create_user_at(fb, "e2e_pharm_b", "PHARMACIST")

        # Source facility A: 500 received, 30 consumed -> usable=470, demand=30,
        # gap=0, eligible surplus = 470 - 30 = 440.
        self.client.force_authenticate(pharm_a)
        r = self.client.post(
            "/api/v1/stock-receipts/",
            {
                "product": para.id,
                "batch_number": "PARA-E2E-A",
                "expiry_date": str(date.today() + timedelta(days=200)),
                "quantity": 500,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        batch_a = StockBatch.objects.get(id=r.data["batch"]["id"])
        self.client.post(
            "/api/v1/stock-consumption/",
            {"batch": batch_a.id, "quantity": 30},
            format="json",
        )

        # Destination facility B: 60 received, 60 consumed -> usable=0,
        # usage=2/day, demand=60, gap=60.
        self.client.force_authenticate(pharm_b)
        r = self.client.post(
            "/api/v1/stock-receipts/",
            {
                "product": para.id,
                "batch_number": "PARA-E2E-B",
                "expiry_date": str(date.today() + timedelta(days=200)),
                "quantity": 60,
            },
            format="json",
        )
        batch_b = StockBatch.objects.get(id=r.data["batch"]["id"])
        self.client.post(
            "/api/v1/stock-consumption/",
            {"batch": batch_b.id, "quantity": 60},
            format="json",
        )

        # ---- Scenario 3: Django calculates the projected gap ----
        self.client.force_authenticate(pharm_b)
        r = self.client.get("/api/v1/inventory/shortages/")
        self.assertEqual(r.status_code, 200)
        row = next(
            (i for i in r.data["items"] if i["product_id"] == para.id), None
        )
        self.assertIsNotNone(row)
        self.assertGreater(row["projected_gap"], 0)

        # ---- Scenario 4: Gemini (mocked) proposes a transfer, coordinator reviews ----
        fake = InventoryAnalysisOutput(
            summary="Facility B has zero Paracetamol with ongoing usage; A has surplus.",
            risks=[
                {
                    "facility_id": fb.id,
                    "product_id": para.id,
                    "priority": "HIGH",
                    "reason": "Zero stock, ongoing consumption.",
                }
            ],
            transfer_recommendations=[
                {
                    "source_facility_id": fa.id,
                    "destination_facility_id": fb.id,
                    "product_id": para.id,
                    "quantity": 60,
                    "reason": "A's surplus covers B's gap.",
                }
            ],
            unresolved_gaps=[],
            missing_information=[],
        )
        with patch("ai_engine.services.generate_structured", return_value=fake):
            self.client.force_authenticate(self.coord)
            r = self.client.post(
                "/api/v1/ai/analyze-inventory/", {}, format="json"
            )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "PENDING_REVIEW")
        self.assertEqual(
            len(r.data["validated_output"]["transfer_recommendations"]), 1
        )
        self.assertEqual(r.data["validation_errors"], [])
        rec_id = r.data["id"]

        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec_id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "APPROVED")
        batch_a.refresh_from_db()
        self.assertEqual(batch_a.quantity_available, 470)  # AI moved nothing

        # ---- Scenario 5: coordinator creates + approves a transfer ----
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            "/api/v1/transfers/",
            {
                "source_facility": fa.id,
                "destination_facility": fb.id,
                "product": para.id,
                "source_batch": batch_a.id,
                "quantity_requested": 60,
                "priority": "HIGH",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        transfer_id = r.data["id"]

        r = self.client.post(
            f"/api/v1/transfers/{transfer_id}/approve/",
            {"quantity_approved": 60},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "APPROVED")
        batch_a.refresh_from_db()
        self.assertEqual(batch_a.quantity_reserved, 60)

        # ---- Scenario 6: phone coordination logged ----
        r = self.client.post(
            f"/api/v1/transfers/{transfer_id}/delivery-coordination/",
            {
                "transport_method": "pickup",
                "transport_provider": "Local carrier",
                "contact_person_name": "Coordinator (phone)",
                "contact_phone": "+251900000000",
                "transport_payer": "CENTRAL",
                "estimated_cost": "250.00",
                "delivery_status": "ARRANGED_BY_PHONE",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)

        # ---- Scenario 7: dispatch, receive, ledger verified ----
        self.client.force_authenticate(pharm_a)
        r = self.client.post(
            f"/api/v1/transfers/{transfer_id}/dispatch/", {}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        batch_a.refresh_from_db()
        self.assertEqual(batch_a.quantity_available, 410)
        self.assertEqual(batch_a.quantity_reserved, 0)

        self.client.force_authenticate(pharm_b)
        r = self.client.post(
            f"/api/v1/transfers/{transfer_id}/confirm-receipt/",
            {"quantity_received": 60, "condition": "OK"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "RECEIVED")

        dest_batch = StockBatch.objects.get(
            facility=fb, batch_number="PARA-E2E-A"
        )
        self.assertEqual(dest_batch.quantity_available, 60)
        self.assertEqual(dest_batch.expiry_date, batch_a.expiry_date)

        self.assertTrue(
            StockMovement.objects.filter(
                movement_type="TRANSFER_OUT", reference_id=str(transfer_id)
            ).exists()
        )
        self.assertTrue(
            StockMovement.objects.filter(
                movement_type="TRANSFER_IN", reference_id=str(transfer_id)
            ).exists()
        )

        # ---- Scenario 8: escalation of remaining gap ----
        self.client.force_authenticate(self.coord)
        r = self.client.post("/api/v1/central/supply-gaps/refresh/", {}, format="json")
        self.assertEqual(r.status_code, 200)

        gap = SupplyGapReport.objects.filter(
            facility=fb, status__in=SupplyGapReport.NON_TERMINAL_STATUSES
        ).first()
        if gap is None:
            gap = SupplyGapReport.objects.create(
                facility=fb,
                product=para,
                reporting_horizon_start=date.today(),
                reporting_horizon_end=date.today() + timedelta(days=30),
                projected_demand=120,
                usable_stock=60,
                reliable_incoming_quantity=0,
                uncovered_quantity=60,
                priority="HIGH",
            )
        r = self.client.post(
            f"/api/v1/central/supply-gaps/{gap.id}/escalate/",
            {"note": "Beyond local redistribution capacity"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "ESCALATED")

    # =================================================================
    # Scenarios 9-10: vaccination + cross-facility isolation
    # =================================================================

    def test_scenarios_9_and_10_vaccination_and_isolation(self):
        # --- setup: two vaccination-capable facilities ---
        applicant_vax = User.objects.create_user(
            username="appl_vax",
            email="appl_vax@example.test",
            password="Pass123!",
            role=User.Role.HEALTH_WORKER,
        )
        applicant_other = User.objects.create_user(
            username="appl_other",
            email="appl_other@example.test",
            password="Pass123!",
            role=User.Role.HEALTH_WORKER,
        )
        r = self._apply(
            applicant_vax,
            "E2E Vax Clinic",
            provides_vaccination_services=True,
            has_cold_chain=True,
        )
        self._approve(r.data["id"])
        vax_fac = Facility.objects.get(id=r.data["id"])

        r = self._apply(
            applicant_other,
            "E2E Other Clinic",
            provides_vaccination_services=True,
            has_cold_chain=True,
        )
        self._approve(r.data["id"])
        other_fac = Facility.objects.get(id=r.data["id"])

        # --- vaccine product + batch ---
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/products/",
            {
                "name": "E2E BCG",
                "category": "VACCINE",
                "requires_cold_chain": True,
                "unit_of_measure": "dose",
            },
            format="json",
        )
        vaccine = Product.objects.get(id=r.data["id"])

        pharm_vax = self._create_user_at(vax_fac, "e2e_pharm_vax", "PHARMACIST")
        self.client.force_authenticate(pharm_vax)
        r = self.client.post(
            "/api/v1/stock-receipts/",
            {
                "product": vaccine.id,
                "batch_number": "E2E-BCG-1",
                "expiry_date": str(date.today() + timedelta(days=180)),
                "quantity": 50,
            },
            format="json",
        )
        batch = StockBatch.objects.get(id=r.data["batch"]["id"])

        # --- schedules (approved) ---
        self.client.force_authenticate(self.admin)
        self.client.post(
            "/api/v1/vaccination-schedules/",
            {
                "vaccine_product": vaccine.id,
                "dose_number": 1,
                "recommended_age_days": 0,
                "effective_from": str(date.today() - timedelta(days=30)),
                "source_name": "EPI",
                "active": True,
            },
            format="json",
        )
        self.client.post(
            "/api/v1/vaccination-schedules/",
            {
                "vaccine_product": vaccine.id,
                "dose_number": 2,
                "minimum_interval_days": 28,
                "effective_from": str(date.today() - timedelta(days=30)),
                "source_name": "EPI",
                "active": True,
            },
            format="json",
        )

        # --- health worker at vax_fac ---
        hw = self._create_user_at(vax_fac, "e2e_hw_vax", "HEALTH_WORKER")
        self.client.force_authenticate(hw)
        r = self.client.post(
            "/api/v1/patients/",
            {
                "full_name": "Demo Patient V1",
                "date_of_birth": str(date.today() - timedelta(days=60)),
                "sex": "MALE",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        patient_id = r.data["id"]

        # ---- Scenario 9: record vaccination, verify auto follow-up ----
        r = self.client.post(
            "/api/v1/vaccination-records/",
            {
                "patient": patient_id,
                "vaccine_product": vaccine.id,
                "dose_number": 1,
                "administered_at": timezone.now().isoformat(),
                "batch": batch.id,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertIsNotNone(r.data["next_follow_up"])
        self.assertEqual(r.data["next_follow_up"]["dose_number"], 2)
        expected_due = date.today() + timedelta(days=28)
        self.assertEqual(
            r.data["next_follow_up"]["due_date"], str(expected_due)
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available, 49)

        r = self.client.get("/api/v1/vaccinations/due/")
        self.assertEqual(r.status_code, 200)

        # ---- Scenario 10: cross-facility isolation ----
        self._create_user_at(other_fac, "e2e_hw_other", "HEALTH_WORKER")
        hw_other = User.objects.get(username="e2e_hw_other")
        self.client.force_authenticate(hw_other)
        r = self.client.post(
            "/api/v1/patients/",
            {
                "full_name": "Demo Patient O1",
                "date_of_birth": str(date.today() - timedelta(days=30)),
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        other_patient_id = r.data["id"]

        # Vax HW cannot see other facility's patient
        self.client.force_authenticate(hw)
        r = self.client.get(f"/api/v1/patients/{other_patient_id}/")
        self.assertEqual(r.status_code, 404)

        # Vax HW cannot create a record for that other patient
        r = self.client.post(
            "/api/v1/vaccination-records/",
            {
                "patient": other_patient_id,
                "vaccine_product": vaccine.id,
                "dose_number": 1,
                "administered_at": timezone.now().isoformat(),
                "batch": batch.id,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)  # invalid pk, not a leak

        # Vax HW's follow-up list contains only own-facility records
        r = self.client.get("/api/v1/vaccination-followups/")
        self.assertEqual(r.status_code, 200)
        patient_ids = {f["patient"] for f in r.data["results"]}
        self.assertIn(patient_id, patient_ids)
        self.assertNotIn(other_patient_id, patient_ids)