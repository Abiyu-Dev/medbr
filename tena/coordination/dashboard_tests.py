from datetime import date, timedelta

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from coordination.models import SupplyGapReport
from facilities.models import Facility
from inventory.models import Product, StockBatch
from inventory.services import receive_stock
from vaccinations.models import VaccineFollowUp


def _mk_user(username, role, facility=None):
    return User.objects.create_user(
        username=username,
        password="TestPass123!",
        email=f"{username}@x.com",
        role=role,
        facility=facility,
    )


def _mk_facility(name="F"):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=Facility.Status.APPROVED,
        has_cold_chain=True,
    )


class CentralDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.fac = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fac)

    def test_requires_auth(self):
        r = self.client.get("/api/v1/dashboard/central-summary/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_facility_user_forbidden(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/dashboard/central-summary/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_ok(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/dashboard/central-summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_coordinator_ok(self):
        self.client.force_authenticate(self.coord)
        r = self.client.get("/api/v1/dashboard/central-summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_payload_shape(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/dashboard/central-summary/")
        for key in (
            "as_of",
            "facilities",
            "stock",
            "top_gaps",
            "near_expiry_redistribution",
            "transfers",
            "supply_gaps",
            "deliveries",
            "vaccinations",
        ):
            self.assertIn(key, r.data)

    def test_facility_counts_reflect_status(self):
        Facility.objects.create(
            name="Pend", facility_type="CLINIC", region="X", status="PENDING"
        )
        Facility.objects.create(
            name="Susp", facility_type="CLINIC", region="X", status="SUSPENDED"
        )
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/dashboard/central-summary/")
        self.assertEqual(r.data["facilities"]["pending_applications"], 1)
        self.assertEqual(r.data["facilities"]["suspended"], 1)
        # Home + Suspended are APPROVED? No — Suspended is separate status. Only Home is APPROVED active.
        self.assertEqual(r.data["facilities"]["approved"], 1)

        def test_top_gaps_only_critical_high(self):
            p1 = Product.objects.create(name="P1", category="MEDICINE")
            p2 = Product.objects.create(name="P2", category="MEDICINE")
            SupplyGapReport.objects.create(
                facility=self.fac, product=p1,
                reporting_horizon_start=date.today(),
                reporting_horizon_end=date.today() + timedelta(days=30),
                projected_demand=100, usable_stock=10,
                reliable_incoming_quantity=0, uncovered_quantity=90,
                priority="CRITICAL",
            )
            SupplyGapReport.objects.create(
                facility=self.fac, product=p2,
                reporting_horizon_start=date.today(),
                reporting_horizon_end=date.today() + timedelta(days=30),
                projected_demand=100, usable_stock=90,
                reliable_incoming_quantity=0, uncovered_quantity=10,
                priority="LOW",
            )
            self.client.force_authenticate(self.coord)
            r = self.client.get("/api/v1/dashboard/central-summary/")
            priorities = [g["priority"] for g in r.data["top_gaps"]]
            self.assertIn("CRITICAL", priorities)
            self.assertNotIn("LOW", priorities)