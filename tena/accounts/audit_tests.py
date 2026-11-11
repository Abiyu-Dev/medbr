from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AuditLog, User
from accounts.services import log_audit
from facilities.models import Facility


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
    )


class AuditEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("Alpha")
        self.fb = _mk_facility("Beta")
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.mgr_a = _mk_user("mgrA", User.Role.FACILITY_MANAGER, facility=self.fa)
        self.mgr_b = _mk_user("mgrB", User.Role.FACILITY_MANAGER, facility=self.fb)
        self.pharm_a = _mk_user("pharmA", User.Role.PHARMACIST, facility=self.fa)

        # Seed audit entries with a mix of actions/entities
        log_audit(self.admin, "FACILITY_APPROVED", "Facility", self.fa.id)
        log_audit(self.admin, "FACILITY_APPROVED", "Facility", self.fb.id)
        log_audit(self.pharm_a, "TRANSFER_REQUESTED", "TransferRequest", "1")
        log_audit(self.pharm_a, "PATIENT_CREATED", "Patient", "999")
        log_audit(self.coord, "SUPPLY_GAP_ASSIGNED", "SupplyGapReport", "7")

    def test_requires_auth(self):
        r = self.client.get("/api/v1/audit/logs/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_sees_all(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/audit/logs/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], AuditLog.objects.count())

    def test_facility_manager_sees_own_facility(self):
        self.client.force_authenticate(self.mgr_a)
        r = self.client.get("/api/v1/audit/logs/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Should see: FACILITY_APPROVED (for fa, via entity_id), TRANSFER_REQUESTED (actor=pharm_a), PATIENT_CREATED (actor=pharm_a)
        actions = {row["action"] for row in r.data["results"]}
        self.assertIn("FACILITY_APPROVED", actions)
        self.assertIn("TRANSFER_REQUESTED", actions)
        self.assertIn("PATIENT_CREATED", actions)
        # Should NOT see: the coordinator's SUPPLY_GAP_ASSIGNED (actor has no facility) or facility B's approval
        self.assertNotIn("SUPPLY_GAP_ASSIGNED", actions)

    def test_facility_manager_does_not_see_other_facility(self):
        self.client.force_authenticate(self.mgr_b)
        r = self.client.get("/api/v1/audit/logs/")
        actions = [row["action"] for row in r.data["results"]]
        self.assertIn("FACILITY_APPROVED", actions)  # for fb
        # mgr_b should not see TRANSFER_REQUESTED by pharm_a
        entity_ids = {(row["entity_type"], row["entity_id"]) for row in r.data["results"]}
        self.assertNotIn(("TransferRequest", "1"), entity_ids)

    def test_central_excludes_patient_pii(self):
        self.client.force_authenticate(self.coord)
        r = self.client.get("/api/v1/audit/logs/")
        actions = {row["action"] for row in r.data["results"]}
        self.assertNotIn("PATIENT_CREATED", actions)
        self.assertIn("SUPPLY_GAP_ASSIGNED", actions)

    def test_health_worker_sees_only_own_actions(self):
        hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fa)
        log_audit(hw, "PATIENT_CREATED", "Patient", "777")
        self.client.force_authenticate(hw)
        r = self.client.get("/api/v1/audit/logs/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["action"], "PATIENT_CREATED")
        self.assertEqual(r.data["results"][0]["actor"], hw.id)

    def test_filter_by_action(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/audit/logs/?action=FACILITY_APPROVED")
        self.assertEqual(r.data["count"], 2)

    def test_filter_by_entity_type(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/audit/logs/?entity_type=Facility")
        self.assertEqual(r.data["count"], 2)

    def test_read_only(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/audit/logs/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        r = self.client.patch("/api/v1/audit/logs/1/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        r = self.client.delete("/api/v1/audit/logs/1/")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_retrieve_single(self):
        self.client.force_authenticate(self.admin)
        log = AuditLog.objects.first()
        r = self.client.get(f"/api/v1/audit/logs/{log.id}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["id"], log.id)