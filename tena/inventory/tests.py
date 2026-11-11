from datetime import date, timedelta

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AuditLog, User
from facilities.models import Facility
from inventory.models import *
from inventory.services import *

from inventory.transfers import TransferError

from decimal import Decimal

from django.utils import timezone

from inventory.calculations import *
from inventory.models import Equipment

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


def _mk_facility(name="F", has_cold_chain=False, status_=Facility.Status.APPROVED):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=status_,
        has_cold_chain=has_cold_chain,
    )


def _mk_product(name="Paracetamol", category="MEDICINE", requires_cold_chain=False):
    return Product.objects.create(
        name=name, category=category, requires_cold_chain=requires_cold_chain
    )


# ---------------------------------------------------------------------------
# Product endpoint permissions
# ---------------------------------------------------------------------------


class ProductEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST)

    def _payload(self):
        return {
            "name": "Amoxicillin",
            "category": "MEDICINE",
            "unit_of_measure": "capsule",
        }

    def test_non_admin_cannot_create(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post("/api/v1/products/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/products/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["name"], "Amoxicillin")

    def test_anonymous_cannot_list(self):
        r = self.client.get("/api/v1/products/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_any_authenticated_can_list(self):
        Product.objects.create(name="A", category="MEDICINE")
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/products/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 1)

    def test_filter_by_category(self):
        Product.objects.create(name="A", category="MEDICINE")
        Product.objects.create(name="V", category="VACCINE")
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/products/?category=VACCINE")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["category"], "VACCINE")

    def test_non_admin_cannot_patch(self):
        p = Product.objects.create(name="A", category="MEDICINE")
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/products/{p.id}/", {"active": False}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


class StockReceiptApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()

    def _payload(self, **over):
        data = {
            "product": self.product.id,
            "batch_number": "B001",
            "expiry_date": str(date.today() + timedelta(days=180)),
            "quantity": 100,
        }
        data.update(over)
        return data

    def test_creates_batch_and_movement(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post("/api/v1/stock-receipts/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["batch"]["quantity_available"], 100)
        self.assertEqual(r.data["movement"]["movement_type"], "RECEIPT")
        self.assertFalse(r.data["replayed"])
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_receipt_to_existing_batch_increments(self):
        self.client.force_authenticate(self.pharm)
        self.client.post("/api/v1/stock-receipts/", self._payload(), format="json")
        r = self.client.post(
            "/api/v1/stock-receipts/", self._payload(quantity=50), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["batch"]["quantity_available"], 150)
        self.assertEqual(StockBatch.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_receipt_with_different_expiry_conflicts(self):
        self.client.force_authenticate(self.pharm)
        self.client.post("/api/v1/stock-receipts/", self._payload(), format="json")
        r = self.client.post(
            "/api/v1/stock-receipts/",
            self._payload(expiry_date=str(date.today() + timedelta(days=365))),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "stock_error")

    def test_receipt_rejects_past_expiry(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-receipts/",
            self._payload(expiry_date=str(date.today() - timedelta(days=1))),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_receipt_cold_chain_mismatch(self):
        vaccine = _mk_product("BCG", category="VACCINE", requires_cold_chain=True)
        self.client.force_authenticate(self.pharm)  # facility.has_cold_chain=False
        r = self.client.post(
            "/api/v1/stock-receipts/",
            self._payload(product=vaccine.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cold chain", str(r.data).lower())

    def test_receipt_idempotency(self):
        self.client.force_authenticate(self.pharm)
        key = "abc-123"
        r1 = self.client.post(
            "/api/v1/stock-receipts/",
            self._payload(idempotency_key=key),
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(
            "/api/v1/stock-receipts/",
            self._payload(idempotency_key=key),
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(r2.data["replayed"])
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockBatch.objects.get().quantity_available, 100)

    def test_requires_approved_facility(self):
        loose = _mk_user("loose", User.Role.PHARMACIST)  # no facility
        self.client.force_authenticate(loose)
        r = self.client.post("/api/v1/stock-receipts/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "no_facility")

    def test_health_worker_cannot_receive(self):
        hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.facility)
        self.client.force_authenticate(hw)
        r = self.client.post("/api/v1/stock-receipts/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------


class StockConsumptionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B001",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=self.pharm,
        )

    def _payload(self, **over):
        data = {"batch": self.batch.id, "quantity": 10}
        data.update(over)
        return data

    def test_consumption_reduces_available(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-consumption/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 90)
        self.assertEqual(r.data["movement"]["movement_type"], "CONSUMPTION")
        self.assertEqual(r.data["movement"]["direction"], "OUT")

    def test_consumption_over_available_fails(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-consumption/", self._payload(quantity=999), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "stock_error")
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 100)

    def test_consumption_on_expired_batch_fails(self):
        self.batch.expiry_date = date.today() - timedelta(days=1)
        self.batch.save()
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-consumption/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", str(r.data).lower())

    def test_consumption_on_quarantined_batch_fails(self):
        self.batch.storage_status = StockBatch.StorageStatus.QUARANTINED
        self.batch.save()
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-consumption/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_consumption_idempotency(self):
        self.client.force_authenticate(self.pharm)
        r1 = self.client.post(
            "/api/v1/stock-consumption/",
            self._payload(idempotency_key="c-1"),
            format="json",
        )
        r2 = self.client.post(
            "/api/v1/stock-consumption/",
            self._payload(idempotency_key="c-1"),
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(r2.data["replayed"])
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 90)

    def test_cross_facility_batch_looks_invalid(self):
        other = _mk_facility("Other")
        other_batch, _, _ = receive_stock(
            facility=other,
            product=self.product,
            batch_number="BO-1",
            expiry_date=date.today() + timedelta(days=90),
            quantity=20,
            performed_by=self.pharm,
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-consumption/",
            {"batch": other_batch.id, "quantity": 1},
            format="json",
        )
        # Should look like a non-existent batch to the caller
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("batch", r.data)


# ---------------------------------------------------------------------------
# Wastage
# ---------------------------------------------------------------------------


class StockWastageApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B001",
            expiry_date=date.today() + timedelta(days=10),
            quantity=50,
            performed_by=self.pharm,
        )

    def test_wastage_requires_reason(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-wastage/",
            {"batch": self.batch.id, "quantity": 5},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wastage_reduces_available(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-wastage/",
            {"batch": self.batch.id, "quantity": 5, "reason": "Broken vial"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 45)
        self.assertEqual(r.data["movement"]["movement_type"], "WASTAGE")

    def test_wastage_allowed_on_expired_batch(self):
        self.batch.expiry_date = date.today() - timedelta(days=1)
        self.batch.save()
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-wastage/",
            {"batch": self.batch.id, "quantity": 50, "reason": "Expired"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 0)

    def test_wastage_over_available_fails(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-wastage/",
            {"batch": self.batch.id, "quantity": 999, "reason": "Broken"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------


class StockAdjustmentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.manager = _mk_user("mgr", User.Role.FACILITY_MANAGER, facility=self.facility)
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B001",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=self.pharm,
        )

    def _payload(self, **over):
        data = {
            "batch": self.batch.id,
            "quantity": 5,
            "direction": "IN",
            "reason": "Recount correction",
        }
        data.update(over)
        return data

    def test_pharmacist_cannot_adjust(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-adjustments/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_adjust_in(self):
        self.client.force_authenticate(self.manager)
        r = self.client.post(
            "/api/v1/stock-adjustments/", self._payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 105)
        self.assertEqual(r.data["movement"]["movement_type"], "ADJUSTMENT")
        self.assertTrue(
            AuditLog.objects.filter(action="STOCK_ADJUSTED").exists()
        )

    def test_admin_can_adjust(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/stock-adjustments/",
            self._payload(direction="OUT", quantity=10),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 90)

    def test_adjustment_requires_reason(self):
        self.client.force_authenticate(self.manager)
        r = self.client.post(
            "/api/v1/stock-adjustments/",
            {"batch": self.batch.id, "quantity": 1, "direction": "OUT"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_adjustment_out_over_available_fails(self):
        self.client.force_authenticate(self.manager)
        r = self.client.post(
            "/api/v1/stock-adjustments/",
            self._payload(direction="OUT", quantity=999),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Scoping & ledger
# ---------------------------------------------------------------------------


class StockScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("A")
        self.fb = _mk_facility("B")
        self.pharm_a = _mk_user("pa", User.Role.PHARMACIST, facility=self.fa)
        self.pharm_b = _mk_user("pb", User.Role.PHARMACIST, facility=self.fb)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.product = _mk_product()

        self.batch_a, _, _ = receive_stock(
            facility=self.fa,
            product=self.product,
            batch_number="BA",
            expiry_date=date.today() + timedelta(days=180),
            quantity=10,
            performed_by=self.pharm_a,
        )
        self.batch_b, _, _ = receive_stock(
            facility=self.fb,
            product=self.product,
            batch_number="BB",
            expiry_date=date.today() + timedelta(days=180),
            quantity=20,
            performed_by=self.pharm_b,
        )

    def test_pharmacist_sees_only_own_batches(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get("/api/v1/batches/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["id"], self.batch_a.id)

    def test_admin_sees_all_batches(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/batches/")
        self.assertEqual(r.data["count"], 2)

    def test_pharmacist_cannot_get_other_batch(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get(f"/api/v1/batches/{self.batch_b.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_sees_only_own_movements(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get("/api/v1/stock-movements/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["facility_id"], self.fa.id)


class BatchPatchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=10,
            performed_by=self.pharm,
        )

    def test_patch_quarantine(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/batches/{self.batch.id}/",
            {"storage_status": "QUARANTINED"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.storage_status, "QUARANTINED")
        self.assertTrue(
            AuditLog.objects.filter(action="BATCH_STORAGE_STATUS_CHANGED").exists()
        )

    def test_cannot_patch_quantity(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/batches/{self.batch.id}/",
            {"quantity_available": 9999},
            format="json",
        )
        # unknown fields are ignored by DRF; quantity stays
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 10)

    def test_no_post_endpoint(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/batches/",
            {"batch_number": "X"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class StockMovementLedgerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=50,
            performed_by=self.pharm,
        )
        consume_stock(batch=self.batch, quantity=10, performed_by=self.pharm)

    def test_no_manual_movement_creation(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/stock-movements/",
            {"batch": self.batch.id, "movement_type": "RECEIPT", "quantity": 999},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_no_movement_update(self):
        mv = StockMovement.objects.first()
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/stock-movements/{mv.id}/",
            {"quantity": 999},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_ledger_reflects_operations(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/stock-movements/")
        self.assertEqual(r.data["count"], 2)
        types = sorted(x["movement_type"] for x in r.data["results"])
        self.assertEqual(types, ["CONSUMPTION", "RECEIPT"])


class StockServiceUnitTests(TestCase):
    """Direct service tests — no HTTP."""

    def setUp(self):
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()

    def test_consume_stock_rejects_zero(self):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=5,
            performed_by=self.pharm,
        )
        with self.assertRaises(StockError):
            consume_stock(batch=batch, quantity=0, performed_by=self.pharm)

    def test_wastage_requires_reason(self):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=5,
            performed_by=self.pharm,
        )
        with self.assertRaises(StockError):
            record_wastage(
                batch=batch, quantity=1, reason="  ", performed_by=self.pharm
            )

    def test_adjustment_direction_must_be_valid(self):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=5,
            performed_by=self.pharm,
        )
        with self.assertRaises(StockError):
            adjust_stock(
                batch=batch,
                quantity=1,
                direction="SIDEWAYS",
                reason="x",
                performed_by=self.pharm,
            )




# ---------------------------------------------------------------------------
# M4 additions
# ---------------------------------------------------------------------------




def _consume(facility, batch, qty, user, days_ago=0):
    """Helper: create a CONSUMPTION movement, backdated if requested."""
    mv, _ = consume_stock(batch=batch, quantity=qty, performed_by=user)
    if days_ago:
        mv.occurred_at = timezone.now() - timedelta(days=days_ago)
        mv.save(update_fields=["occurred_at"])
    return mv


# ----------------------- Calculation service tests -----------------------


class UsableStockCalcTests(TestCase):
    def setUp(self):
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()

    def _receive(self, batch_number, qty, expiry, status="OK"):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number=batch_number,
            expiry_date=expiry,
            quantity=qty,
            performed_by=self.pharm,
        )
        if status != "OK":
            batch.storage_status = status
            batch.save()
        return batch

    def test_usable_includes_only_ok_non_expired(self):
        self._receive("A", 100, date.today() + timedelta(days=180))
        self._receive("B", 50, date.today() + timedelta(days=180), status="QUARANTINED")
        self._receive("C", 40, date.today() - timedelta(days=1))  # expired
        self._receive("D", 60, date.today() + timedelta(days=180), status="DAMAGED")
        self.assertEqual(get_usable_stock(self.facility, self.product), 100)

    def test_usable_zero_when_no_batches(self):
        self.assertEqual(get_usable_stock(self.facility, self.product), 0)

    def test_reserved_stock(self):
        b = self._receive("A", 100, date.today() + timedelta(days=180))
        b.quantity_reserved = 15
        b.save()
        self.assertEqual(get_reserved_stock(self.facility, self.product), 15)


class DailyUsageCalcTests(TestCase):
    def setUp(self):
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=1000,
            performed_by=self.pharm,
        )

    def test_returns_none_without_usage(self):
        self.assertIsNone(
            get_estimated_daily_usage(self.facility, self.product, window_days=30)
        )

    def test_average_over_window(self):
        _consume(self.facility, self.batch, 30, self.pharm)
        _consume(self.facility, self.batch, 60, self.pharm)
        # 90 / 30 = 3.0
        daily = get_estimated_daily_usage(self.facility, self.product, window_days=30)
        self.assertEqual(daily, Decimal("3.0000"))

    def test_excludes_old_movements(self):
        _consume(self.facility, self.batch, 30, self.pharm)
        _consume(self.facility, self.batch, 60, self.pharm, days_ago=45)
        daily = get_estimated_daily_usage(self.facility, self.product, window_days=30)
        # Only 30 in window → 1.0/day
        self.assertEqual(daily, Decimal("1.0000"))

    def test_wastage_not_counted(self):
        record_wastage(
            batch=self.batch, quantity=20, reason="broken", performed_by=self.pharm
        )
        self.assertIsNone(
            get_estimated_daily_usage(self.facility, self.product, window_days=30)
        )


class NearExpiryCalcTests(TestCase):
    def setUp(self):
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()

    def _receive(self, batch_number, qty, expiry, status="OK"):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number=batch_number,
            expiry_date=expiry,
            quantity=qty,
            performed_by=self.pharm,
        )
        if status != "OK":
            batch.storage_status = status
            batch.save()
        return batch

    def test_only_within_window(self):
        self._receive("soon", 40, date.today() + timedelta(days=20))
        self._receive("far", 100, date.today() + timedelta(days=200))
        self._receive("expired", 10, date.today() - timedelta(days=1))
        self._receive("quar", 5, date.today() + timedelta(days=20), status="QUARANTINED")
        rows = list(get_near_expiry_batches(self.facility, days=90))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].batch_number, "soon")

    def test_zero_quantity_excluded(self):
        b = self._receive("soon", 40, date.today() + timedelta(days=20))
        b.quantity_available = 0
        b.save()
        self.assertEqual(len(list(get_near_expiry_batches(self.facility, days=90))), 0)


class ProductSummaryCalcTests(TestCase):
    def setUp(self):
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=60),
            quantity=400,
            performed_by=self.pharm,
        )

    def test_unknowns_when_no_usage(self):
        summary = get_product_summary(self.facility, self.product)
        self.assertIsNone(summary["projected_demand"])
        self.assertIsNone(summary["projected_gap"])
        self.assertIsNone(summary["days_of_stock"])
        self.assertIsNone(summary["estimated_daily_usage"])
        self.assertEqual(summary["usable_stock"], 400)

    def test_gap_positive_when_demand_exceeds_stock(self):
        # 10/day * 30 days = 300 demand, 100 usable → gap 200
        for _ in range(10):
            _consume(self.facility, self.batch, 30, self.pharm)
        summary = get_product_summary(self.facility, self.product, horizon_days=30)
        self.assertEqual(summary["projected_demand"], 300)
        self.assertEqual(summary["projected_gap"], 200)
        self.assertGreater(summary["days_of_stock"], 0)

    def test_gap_zero_when_stock_sufficient(self):
        # 1/day * 30 days = 30 demand, 100 usable → gap 0
        _consume(self.facility, self.batch, 30, self.pharm)
        summary = get_product_summary(self.facility, self.product, horizon_days=30)
        self.assertEqual(summary["projected_demand"], 30)
        self.assertEqual(summary["projected_gap"], 0)

    def test_gap_zero_with_zero_usable_and_no_usage(self):
        # No movement, but stock still there — gap is unknown, not zero
        self.batch.quantity_available = 0
        self.batch.save()
        summary = get_product_summary(self.facility, self.product)
        self.assertIsNone(summary["projected_gap"])
        self.assertEqual(summary["usable_stock"], 0)


class FacilityProductIdsTests(TestCase):
    def setUp(self):
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.p1 = _mk_product("Paracetamol")
        self.p2 = _mk_product("Amoxicillin")
        self.p3 = _mk_product("BCG", category="VACCINE")

    def test_only_products_touched_by_facility(self):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.p1,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=self.pharm,
        )
        _consume(self.facility, batch, 5, self.pharm)
        ids = get_facility_product_ids(self.facility)
        self.assertIn(self.p1.id, ids)
        self.assertNotIn(self.p2.id, ids)
        self.assertNotIn(self.p3.id, ids)

    def test_product_with_usage_but_no_current_batch_included(self):
        batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.p1,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=10,
            performed_by=self.pharm,
        )
        _consume(self.facility, batch, 10, self.pharm)  # drains it
        # Wipe the batch row by zeroing quantity
        batch.quantity_available = 0
        batch.save()
        ids = get_facility_product_ids(self.facility)
        self.assertIn(self.p1.id, ids)


# ----------------------- /inventory/* endpoints -----------------------


class InventorySummaryEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("Alpha")
        self.fb = _mk_facility("Beta")
        self.pharm_a = _mk_user("pa", User.Role.PHARMACIST, facility=self.fa)
        self.pharm_b = _mk_user("pb", User.Role.PHARMACIST, facility=self.fb)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.product = _mk_product()

        self.batch_a, _, _ = receive_stock(
            facility=self.fa,
            product=self.product,
            batch_number="BA",
            expiry_date=date.today() + timedelta(days=60),
            quantity=1000,
            performed_by=self.pharm_a,
        )
        _consume(self.fa, self.batch_a, 300, self.pharm_a)  # would fail on 100...

    def test_endpoint_requires_auth(self):
        r = self.client.get("/api/v1/inventory/summary/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_facility_user_sees_own_facility(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get("/api/v1/inventory/summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["facility_id"], self.fa.id)
        self.assertEqual(r.data["facility_name"], "Alpha")
        self.assertEqual(r.data["horizon_days"], 30)

    def test_facility_user_cannot_query_other(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get(f"/api/v1/inventory/summary/?facility={self.fb.id}")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(r.data["code"], "forbidden")

    def test_admin_must_pass_facility(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/inventory/summary/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "facility_required")

    def test_admin_can_query_any_facility(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(f"/api/v1/inventory/summary/?facility={self.fa.id}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["facility_id"], self.fa.id)

    def test_coordinator_can_query_any_facility(self):
        self.client.force_authenticate(self.coord)
        r = self.client.get(f"/api/v1/inventory/summary/?facility={self.fa.id}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_admin_missing_facility_404(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/inventory/summary/?facility=9999")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_horizon_returns_400(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get("/api/v1/inventory/summary/?horizon_days=0")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "invalid_query")

    def test_no_facility_user_gets_400(self):
        loose = _mk_user("loose", User.Role.PHARMACIST)
        self.client.force_authenticate(loose)
        r = self.client.get("/api/v1/inventory/summary/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "no_facility")


class InventorySummaryShapeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.product = _mk_product()
        self.batch, _, _ = receive_stock(
            facility=self.facility,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=60),
            quantity=100,
            performed_by=self.pharm,
        )

    def test_product_with_stock_but_no_usage_shows_nulls(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["items"]), 1)
        item = r.data["items"][0]
        self.assertEqual(item["usable_stock"], 100)
        self.assertIsNone(item["projected_demand"])
        self.assertIsNone(item["projected_gap"])
        self.assertIsNone(item["days_of_stock"])
        self.assertEqual(item["incoming_stock"], 0)
        self.assertEqual(item["near_expiry_quantity"], 100)  # expires in 60d, threshold 90d

    def test_product_with_usage_shows_numbers(self):
        for _ in range(10):
            _consume(self.facility, self.batch, 9, self.pharm)
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/summary/")
        item = r.data["items"][0]
        self.assertEqual(item["usable_stock"], 10)
        self.assertIsNotNone(item["projected_demand"])
        self.assertIsNotNone(item["projected_gap"])
        self.assertIsNotNone(item["days_of_stock"])

    def test_custom_near_expiry_window(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/summary/?near_expiry_days=7")
        item = r.data["items"][0]
        self.assertEqual(item["near_expiry_quantity"], 0)  # expires in 60d, window 7d

    def test_products_with_no_batch_and_no_usage_hidden(self):
        _mk_product("NeverTouched")
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/summary/")
        names = {it["product_name"] for it in r.data["items"]}
        self.assertNotIn("NeverTouched", names)


class InventoryShortagesEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.low = _mk_product("Low")
        self.ok = _mk_product("OK")
        self.unknown = _mk_product("Unknown")

        b_low, _, _ = receive_stock(
            facility=self.facility,
            product=self.low,
            batch_number="L1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=5,
            performed_by=self.pharm,
        )
        for _ in range(3):
            _consume(self.facility, b_low, 1, self.pharm)  # 3 consumed in 30d window

        b_ok, _, _ = receive_stock(
            facility=self.facility,
            product=self.ok,
            batch_number="O1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=500,
            performed_by=self.pharm,
        )
        _consume(self.facility, b_ok, 30, self.pharm)  # 1/day, plenty of stock

        receive_stock(
            facility=self.facility,
            product=self.unknown,
            batch_number="U1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=10,
            performed_by=self.pharm,
        )

    def test_only_positive_gaps_appear(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/shortages/?horizon_days=30")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        names = [i["product_name"] for i in r.data["items"]]
        self.assertIn("Low", names)
        self.assertNotIn("OK", names)
        self.assertNotIn("Unknown", names)
        for it in r.data["items"]:
            self.assertGreater(it["projected_gap"], 0)

    def test_sorted_by_gap_descending(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/shortages/")
        gaps = [i["projected_gap"] for i in r.data["items"]]
        self.assertEqual(gaps, sorted(gaps, reverse=True))


class InventoryExpiringEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.facility)
        self.p1 = _mk_product("Soon")
        self.p2 = _mk_product("Later")

        receive_stock(
            facility=self.facility,
            product=self.p1,
            batch_number="SOON-1",
            expiry_date=date.today() + timedelta(days=20),
            quantity=40,
            performed_by=self.pharm,
        )
        receive_stock(
            facility=self.facility,
            product=self.p2,
            batch_number="LATER-1",
            expiry_date=date.today() + timedelta(days=300),
            quantity=60,
            performed_by=self.pharm,
        )

    def test_default_window(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/expiring/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["near_expiry_days"], 90)
        self.assertEqual(len(r.data["batches"]), 1)
        row = r.data["batches"][0]
        self.assertEqual(row["batch_number"], "SOON-1")
        self.assertEqual(row["quantity_available"], 40)
        self.assertEqual(row["days_until_expiry"], 20)

    def test_custom_window(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/expiring/?days=400")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["batches"]), 2)

    def test_narrow_window_returns_nothing(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/expiring/?days=5")
        self.assertEqual(len(r.data["batches"]), 0)

    def test_facility_scoped(self):
        other = _mk_facility("Other")
        pharm_other = _mk_user("po", User.Role.PHARMACIST, facility=other)
        receive_stock(
            facility=other,
            product=self.p1,
            batch_number="OTHER-1",
            expiry_date=date.today() + timedelta(days=10),
            quantity=5,
            performed_by=pharm_other,
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/inventory/expiring/?days=90")
        batch_numbers = [b["batch_number"] for b in r.data["batches"]]
        self.assertNotIn("OTHER-1", batch_numbers)


# ----------------------- Equipment endpoints -----------------------


class EquipmentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("Alpha")
        self.fb = _mk_facility("Beta")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fa)
        self.pharm_b = _mk_user("pharmb", User.Role.PHARMACIST, facility=self.fb)
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fa)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)

    def _payload(self, **over):
        data = {
            "name": "Cold box",
            "category": "cold-chain",
            "asset_identifier": "CB-001",
            "quantity": 2,
            "condition": "OPERATIONAL",
        }
        data.update(over)
        return data

    def test_pharmacist_creates_for_own_facility(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post("/api/v1/equipment/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["facility"], self.fa.id)
        self.assertEqual(r.data["created_by"], self.pharm.id)

    def test_pharmacist_payload_facility_is_ignored(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.post(
            "/api/v1/equipment/",
            self._payload(facility=self.fb.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        # Injected facility wins
        self.assertEqual(r.data["facility"], self.fa.id)

    def test_health_worker_cannot_create(self):
        self.client.force_authenticate(self.hw)
        r = self.client.post("/api/v1/equipment/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_must_specify_facility(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/equipment/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("facility", r.data)

    def test_admin_creates_for_specific_facility(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/equipment/", self._payload(facility=self.fb.id), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["facility"], self.fb.id)

    def test_coordinator_cannot_create(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            "/api/v1/equipment/", self._payload(facility=self.fb.id), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_scoped_to_own_facility(self):
        Equipment.objects.create(
            facility=self.fa, name="A-eq", condition="OPERATIONAL", created_by=self.pharm
        )
        Equipment.objects.create(
            facility=self.fb, name="B-eq", condition="OPERATIONAL", created_by=self.pharm_b
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/equipment/")
        names = [e["name"] for e in r.data["results"]]
        self.assertEqual(names, ["A-eq"])

    def test_admin_sees_all_equipment(self):
        Equipment.objects.create(
            facility=self.fa, name="A-eq", condition="OPERATIONAL", created_by=self.pharm
        )
        Equipment.objects.create(
            facility=self.fb, name="B-eq", condition="OPERATIONAL", created_by=self.pharm_b
        )
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/equipment/")
        self.assertEqual(r.data["count"], 2)

    def test_filter_by_condition(self):
        Equipment.objects.create(
            facility=self.fa, name="OK", condition="OPERATIONAL", created_by=self.pharm
        )
        Equipment.objects.create(
            facility=self.fa, name="BAD", condition="OUT_OF_SERVICE", created_by=self.pharm
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/equipment/?condition=OUT_OF_SERVICE")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["name"], "BAD")

    def test_patch_own(self):
        eq = Equipment.objects.create(
            facility=self.fa, name="A-eq", condition="OPERATIONAL", created_by=self.pharm
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/equipment/{eq.id}/",
            {"condition": "NEEDS_MAINTENANCE"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        eq.refresh_from_db()
        self.assertEqual(eq.condition, "NEEDS_MAINTENANCE")

    def test_cannot_patch_other_facility(self):
        eq = Equipment.objects.create(
            facility=self.fb, name="B-eq", condition="OPERATIONAL", created_by=self.pharm_b
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/equipment/{eq.id}/",
            {"condition": "OUT_OF_SERVICE"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_facility_cannot_be_changed_on_patch(self):
        eq = Equipment.objects.create(
            facility=self.fa, name="A-eq", condition="OPERATIONAL", created_by=self.pharm
        )
        self.client.force_authenticate(self.pharm)
        r = self.client.patch(
            f"/api/v1/equipment/{eq.id}/",
            {"facility": self.fb.id},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        eq.refresh_from_db()
        self.assertEqual(eq.facility, self.fa)


# ===========================================================================
# M5 — Transfers
# ===========================================================================




def _mk_transfer_setup():
    """Create F_A (source) and F_B (destination) each with a pharmacist and a batch."""
    fa = _mk_facility("Source A")
    fb = _mk_facility("Dest B")
    pharm_a = _mk_user("pa_m5", User.Role.PHARMACIST, facility=fa)
    pharm_b = _mk_user("pb_m5", User.Role.PHARMACIST, facility=fb)
    mgr_a = _mk_user("mgra_m5", User.Role.FACILITY_MANAGER, facility=fa)
    mgr_b = _mk_user("mgrb_m5", User.Role.FACILITY_MANAGER, facility=fb)
    coord = _mk_user("coord_m5", User.Role.CENTRAL_COORDINATOR)
    admin = _mk_user("admin_m5", User.Role.SYSTEM_ADMIN)
    product = _mk_product("Transfer-Product")
    batch_a, _, _ = receive_stock(
        facility=fa,
        product=product,
        batch_number="TB-1",
        expiry_date=date.today() + timedelta(days=180),
        quantity=100,
        performed_by=pharm_a,
    )
    return {
        "fa": fa,
        "fb": fb,
        "pharm_a": pharm_a,
        "pharm_b": pharm_b,
        "mgr_a": mgr_a,
        "mgr_b": mgr_b,
        "coord": coord,
        "admin": admin,
        "product": product,
        "batch_a": batch_a,
    }


class TransferCreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.s = _mk_transfer_setup()

    def _payload(self, **over):
        data = {
            "source_facility": self.s["fa"].id,
            "destination_facility": self.s["fb"].id,
            "product": self.s["product"].id,
            "source_batch": self.s["batch_a"].id,
            "quantity_requested": 40,
            "priority": "HIGH",
        }
        data.update(over)
        return data

    def test_facility_can_request_into_own_facility(self):
        self.client.force_authenticate(self.s["pharm_b"])
        r = self.client.post("/api/v1/transfers/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "REQUESTED")
        self.assertEqual(TransferRequest.objects.count(), 1)

    def test_facility_cannot_request_for_unrelated_facilities(self):
        pharm_c = _mk_user("pc_m5", User.Role.PHARMACIST, facility=_mk_facility("C"))
        self.client.force_authenticate(pharm_c)
        r = self.client.post("/api/v1/transfers/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_central_can_create_any(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post("/api/v1/transfers/", self._payload(), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_same_source_destination_rejected(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post(
            "/api/v1/transfers/",
            self._payload(destination_facility=self.s["fa"].id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "transfer_error")

    def test_batch_must_belong_to_source(self):
        self.client.force_authenticate(self.s["coord"])
        other_batch = StockBatch.objects.create(
            facility=self.s["fb"],
            product=self.s["product"],
            batch_number="WRONG",
            expiry_date=date.today() + timedelta(days=180),
            quantity_available=10,
        )
        r = self.client.post(
            "/api/v1/transfers/",
            self._payload(source_batch=other_batch.id),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quantity_over_free_stock_rejected(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post(
            "/api/v1/transfers/",
            self._payload(quantity_requested=999),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TransferApproveRejectTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.s = _mk_transfer_setup()
        self.transfer = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=40,
            priority="HIGH",
            requested_by=self.s["pharm_b"],
        )

    def test_source_manager_approves_and_reserves(self):
        self.client.force_authenticate(self.s["mgr_a"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/",
            {"quantity_approved": 40},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["status"], "APPROVED")
        self.s["batch_a"].refresh_from_db()
        self.assertEqual(self.s["batch_a"].quantity_reserved, 40)
        self.assertEqual(self.s["batch_a"].quantity_available, 100)  # unchanged

    def test_dest_manager_cannot_approve(self):
        self.client.force_authenticate(self.s["mgr_b"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_central_approves(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_approve_over_free_stock_fails(self):
        self.client.force_authenticate(self.s["coord"])

        # First transfer: 80 units, fully approved → reserved = 80, free = 20
        t1 = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=80,
            priority="HIGH",
            requested_by=self.s["pharm_b"],
        )
        r1 = self.client.post(
            f"/api/v1/transfers/{t1.id}/approve/",
            {"quantity_approved": 80},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.s["batch_a"].refresh_from_db()
        self.assertEqual(self.s["batch_a"].quantity_reserved, 80)

        # Second transfer: 80 units → only 20 free → must fail
        t2 = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=80,
            priority="MEDIUM",
            requested_by=self.s["pharm_b"],
        )
        r2 = self.client.post(
            f"/api/v1/transfers/{t2.id}/approve/",
            {"quantity_approved": 80},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r2.data["code"], "transfer_error")

        # Reservation stays at 80 — the failed approve did not partially reserve
        self.s["batch_a"].refresh_from_db()
        self.assertEqual(self.s["batch_a"].quantity_reserved, 80)

    def test_cannot_approve_twice(self):
        self.client.force_authenticate(self.s["coord"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/", {}, format="json"
        )
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_reject_requires_reason(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/reject/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_succeeds(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/reject/",
            {"rejection_reason": "Not urgent"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, "REJECTED")
        self.assertEqual(self.transfer.rejection_reason, "Not urgent")


class TransferDispatchReceiptTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.s = _mk_transfer_setup()
        self.transfer = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=40,
            priority="HIGH",
            requested_by=self.s["pharm_b"],
        )
        self.client.force_authenticate(self.s["coord"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/",
            {"quantity_approved": 40},
            format="json",
        )
        self.transfer.refresh_from_db()

    def test_dispatch_reduces_source_and_releases_reservation(self):
        self.client.force_authenticate(self.s["pharm_a"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/",
            {"notes": "Left at 9am"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["status"], "DISPATCHED")
        self.s["batch_a"].refresh_from_db()
        self.assertEqual(self.s["batch_a"].quantity_available, 60)
        self.assertEqual(self.s["batch_a"].quantity_reserved, 0)
        mv = StockMovement.objects.filter(
            movement_type="TRANSFER_OUT", reference_id=str(self.transfer.id)
        ).first()
        self.assertIsNotNone(mv)
        self.assertEqual(mv.quantity, 40)
        self.assertEqual(mv.direction, "OUT")

    def test_dest_staff_cannot_dispatch(self):
        self.client.force_authenticate(self.s["pharm_b"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_dispatch_twice_conflicts(self):
        self.client.force_authenticate(self.s["pharm_a"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_receipt_creates_destination_batch_and_movement(self):
        self.client.force_authenticate(self.s["pharm_a"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )

        self.client.force_authenticate(self.s["pharm_b"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/confirm-receipt/",
            {"quantity_received": 40, "condition": "OK"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["status"], "RECEIVED")
        dest_batch = StockBatch.objects.get(
            facility=self.s["fb"], batch_number="TB-1"
        )
        self.assertEqual(dest_batch.quantity_available, 40)
        self.assertEqual(dest_batch.expiry_date, self.s["batch_a"].expiry_date)
        mv = StockMovement.objects.filter(
            movement_type="TRANSFER_IN", reference_id=str(self.transfer.id)
        ).first()
        self.assertIsNotNone(mv)
        self.assertEqual(mv.quantity, 40)

    def test_receipt_with_damaged_quarantines_batch(self):
        self.client.force_authenticate(self.s["pharm_a"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        self.client.force_authenticate(self.s["pharm_b"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/confirm-receipt/",
            {"quantity_received": 40, "condition": "DAMAGED"},
            format="json",
        )
        dest_batch = StockBatch.objects.get(
            facility=self.s["fb"], batch_number="TB-1"
        )
        self.assertEqual(dest_batch.storage_status, "DAMAGED")

    def test_short_receipt_creates_discrepancy_audit(self):
        self.client.force_authenticate(self.s["pharm_a"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        self.client.force_authenticate(self.s["pharm_b"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/confirm-receipt/",
            {"quantity_received": 35},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        dest_batch = StockBatch.objects.get(
            facility=self.s["fb"], batch_number="TB-1"
        )
        self.assertEqual(dest_batch.quantity_available, 35)
        self.assertTrue(
            AuditLog.objects.filter(action="TRANSFER_DISCREPANCY").exists()
        )

    def test_receipt_over_approved_rejected(self):
        self.client.force_authenticate(self.s["pharm_a"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        self.client.force_authenticate(self.s["pharm_b"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/confirm-receipt/",
            {"quantity_received": 100},  # > 40 approved
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_receipt_expiry_conflict_rejected(self):
        # Pre-create a dest batch with the same batch_number but a different expiry
        StockBatch.objects.create(
            facility=self.s["fb"],
            product=self.s["product"],
            batch_number="TB-1",
            expiry_date=date.today() + timedelta(days=365),
            quantity_available=5,
        )
        self.client.force_authenticate(self.s["pharm_a"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        self.client.force_authenticate(self.s["pharm_b"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/confirm-receipt/",
            {"quantity_received": 40},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TransferCancelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.s = _mk_transfer_setup()
        self.transfer = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=40,
            priority="HIGH",
            requested_by=self.s["pharm_b"],
        )

    def test_cancel_requested(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/cancel/",
            {"reason": "Duplicate"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, "CANCELLED")

    def test_cancel_approved_releases_reservation(self):
        self.client.force_authenticate(self.s["coord"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/", {}, format="json"
        )
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/cancel/", {}, format="json"
        )
        self.s["batch_a"].refresh_from_db()
        self.assertEqual(self.s["batch_a"].quantity_reserved, 0)

    def test_cannot_cancel_dispatched(self):
        self.client.force_authenticate(self.s["coord"])
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/approve/", {}, format="json"
        )
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/dispatch/", {}, format="json"
        )
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/cancel/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)


class TransferScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.s = _mk_transfer_setup()
        self.transfer = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=40,
            priority="HIGH",
            requested_by=self.s["pharm_b"],
        )

    def test_source_pharmacist_sees_transfer(self):
        self.client.force_authenticate(self.s["pharm_a"])
        r = self.client.get(f"/api/v1/transfers/{self.transfer.id}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_unrelated_facility_cannot_see(self):
        pharm_c = _mk_user("pc_sc", User.Role.PHARMACIST, facility=_mk_facility("C-Sc"))
        self.client.force_authenticate(pharm_c)
        r = self.client.get(f"/api/v1/transfers/{self.transfer.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_central_sees_all(self):
        self.client.force_authenticate(self.s["coord"])
        r = self.client.get("/api/v1/transfers/")
        self.assertEqual(r.data["count"], 1)


# ===========================================================================
# M5 — incoming_stock in inventory summary
# ===========================================================================


class IncomingStockIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.s = _mk_transfer_setup()

    def test_approved_transfer_shows_in_incoming(self):
        # Approve a 40-unit transfer to B
        self.client.force_authenticate(self.s["coord"])
        t = TransferRequest.objects.create(
            source_facility=self.s["fa"],
            destination_facility=self.s["fb"],
            product=self.s["product"],
            source_batch=self.s["batch_a"],
            quantity_requested=40,
            priority="HIGH",
            requested_by=self.s["pharm_b"],
        )
        self.client.post(
            f"/api/v1/transfers/{t.id}/approve/",
            {"quantity_approved": 40},
            format="json",
        )

        # B's inventory summary should show 40 incoming
        self.client.force_authenticate(self.s["coord"])
        r = self.client.get(f"/api/v1/inventory/summary/?facility={self.s['fb'].id}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Find our product's row
        row = next(
            (
                it
                for it in r.data["items"]
                if it["product_id"] == self.s["product"].id
            ),
            None,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["incoming_stock"], 40)