from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from facilities.models import Facility
from inventory.models import Equipment, Product, StockBatch, TransferRequest
from inventory.services import consume_stock, receive_stock
from vaccinations.models import VaccineFollowUp


def _mk_user(username, role, facility=None):
    return User.objects.create_user(
        username=username,
        password="TestPass123!",
        email=f"{username}@x.com",
        role=role,
        facility=facility,
    )


def _mk_facility(name="F", provides_vaccination_services=False):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=Facility.Status.APPROVED,
        provides_vaccination_services=provides_vaccination_services,
        has_cold_chain=True,
    )


def _mk_product(name="Prod", category="MEDICINE"):
    return Product.objects.create(
        name=name,
        category=category,
        requires_cold_chain=False,
        unit_of_measure="dose" if category == "VACCINE" else "tablet",
    )


class FacilityDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("Alpha")
        self.fb = _mk_facility("Beta")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fa)
        self.pharm_b = _mk_user("pharmb", User.Role.PHARMACIST, facility=self.fb)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)

    def test_requires_auth(self):
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_facility_user_gets_own_facility(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["facility"]["id"], self.fa.id)

    def test_central_must_pass_facility_param(self):
        self.client.force_authenticate(self.coord)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "facility_required")

    def test_central_can_query_any_facility(self):
        self.client.force_authenticate(self.coord)
        r = self.client.get(
            f"/api/v1/dashboard/facility-summary/?facility={self.fa.id}"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["facility"]["id"], self.fa.id)

    def test_facility_user_cannot_spoof_facility(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get(
            f"/api/v1/dashboard/facility-summary/?facility={self.fb.id}"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_payload_shape(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        for key in (
            "facility",
            "as_of",
            "inventory",
            "shortages",
            "near_expiry",
            "transfers",
            "vaccinations",
            "equipment",
            "recent_movements",
            "recent_audit",
            "data_freshness",
        ):
            self.assertIn(key, r.data)
        for key in ("total_batches", "usable_units", "products_with_gap", "critical_shortages"):
            self.assertIn(key, r.data["inventory"])

    def test_shortages_appear_when_usage_exceeds_stock(self):
        product = _mk_product("Shortage-Prod")
        batch, _, _ = receive_stock(
            facility=self.fa,
            product=product,
            batch_number="S1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=50,
            performed_by=self.pharm,
        )
        # Consume 40 across 10 days → 4/day, 30-day demand 120, usable 10 → gap 110
        for _ in range(10):
            consume_stock(batch=batch, quantity=4, performed_by=self.pharm)

        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["inventory"]["products_with_gap"], 1)
        self.assertEqual(len(r.data["shortages"]), 1)
        self.assertEqual(r.data["shortages"][0]["product_name"], "Shortage-Prod")
        self.assertGreater(r.data["shortages"][0]["projected_gap"], 0)

    def test_near_expiry_lists_within_window(self):
        p1 = _mk_product("Near")
        receive_stock(
            facility=self.fa,
            product=p1,
            batch_number="NEAR-1",
            expiry_date=date.today() + timedelta(days=30),
            quantity=20,
            performed_by=self.pharm,
        )
        p2 = _mk_product("Far")
        receive_stock(
            facility=self.fa,
            product=p2,
            batch_number="FAR-1",
            expiry_date=date.today() + timedelta(days=300),
            quantity=20,
            performed_by=self.pharm,
        )

        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        names = [row["product_name"] for row in r.data["near_expiry"]]
        self.assertIn("Near", names)
        self.assertNotIn("Far", names)

    def test_incoming_transfers_listed(self):
        product = _mk_product()
        batch_a, _, _ = receive_stock(
            facility=self.fb,
            product=product,
            batch_number="TB1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=self.pharm_b,
        )
        TransferRequest.objects.create(
            source_facility=self.fb,
            destination_facility=self.fa,
            product=product,
            source_batch=batch_a,
            quantity_requested=30,
            quantity_approved=30,
            priority="HIGH",
            requested_by=self.pharm,
            status="APPROVED",
        )

        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        self.assertEqual(len(r.data["transfers"]["incoming"]), 1)
        row = r.data["transfers"]["incoming"][0]
        self.assertEqual(row["peer_facility_id"], self.fb.id)
        self.assertEqual(row["quantity_approved"], 30)

    def test_equipment_counts(self):
        Equipment.objects.create(
            facility=self.fa, name="Fridge", condition="OPERATIONAL"
        )
        Equipment.objects.create(
            facility=self.fa, name="Cold box", condition="OUT_OF_SERVICE"
        )
        Equipment.objects.create(
            facility=self.fa, name="Scale", condition="NEEDS_MAINTENANCE"
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        eq = r.data["equipment"]
        self.assertEqual(eq["total"], 3)
        self.assertEqual(eq["out_of_service"], 1)
        self.assertEqual(eq["needs_maintenance"], 1)

    def test_non_vaccination_facility_shows_zero_vaccination_counts(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/facility-summary/")
        self.assertEqual(r.data["vaccinations"]["due_in_7_days"], 0)
        self.assertEqual(r.data["vaccinations"]["overdue"], 0)