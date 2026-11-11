from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AuditLog, User
from facilities.models import Facility


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_user(username, role, facility=None, password="TestPass123!"):
    return User.objects.create_user(
        username=username,
        password=password,
        email=f"{username}@x.com",
        role=role,
        facility=facility,
    )


def _mk_facility(name="F", status_=Facility.Status.PENDING, **kw):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=status_,
        **kw,
    )


def _auth(client, user):
    client.force_authenticate(user)
    return client


# ---------------------------------------------------------------------------
# Model sanity
# ---------------------------------------------------------------------------


class FacilityModelTests(TestCase):
    def test_defaults(self):
        f = _mk_facility()
        self.assertEqual(f.status, Facility.Status.PENDING)
        self.assertTrue(f.is_active)

    def test_lat_bounds(self):
        f = Facility(
            name="x", facility_type="CLINIC", region="X", latitude=999, longitude=30
        )
        with self.assertRaises(ValidationError):
            f.full_clean()

    def test_lon_bounds(self):
        f = Facility(
            name="x", facility_type="CLINIC", region="X", latitude=9, longitude=999
        )
        with self.assertRaises(ValidationError):
            f.full_clean()


# ---------------------------------------------------------------------------
# Application submission
# ---------------------------------------------------------------------------


class FacilityApplicationSubmitTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.applicant = _mk_user("applicant", User.Role.HEALTH_WORKER)

    def _valid_payload(self):
        return {
            "name": "New Clinic",
            "facility_type": "CLINIC",
            "region": "Addis Ababa",
            "town": "Bole",
            "contact_phone": "+251911000111",
            "latitude": "9.010",
            "longitude": "38.760",
        }

    def test_requires_auth(self):
        r = self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_creates_pending_facility(self):
        _auth(self.client, self.applicant)
        r = self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "PENDING")
        self.assertEqual(r.data["submitted_by"], self.applicant.id)
        f = Facility.objects.get(id=r.data["id"])
        self.assertEqual(f.submitted_by, self.applicant)

    def test_creates_audit_log(self):
        _auth(self.client, self.applicant)
        self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        self.assertEqual(
            AuditLog.objects.filter(action="FACILITY_APPLICATION_SUBMITTED").count(), 1
        )

    def test_rejects_invalid_lat(self):
        _auth(self.client, self.applicant)
        payload = self._valid_payload()
        payload["latitude"] = "999"
        r = self.client.post(
            "/api/v1/facilities/applications/", payload, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_duplicate_pending_submission(self):
        _auth(self.client, self.applicant)
        self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        r = self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "duplicate_application")

    def test_blocks_user_with_facility(self):
        facility = _mk_facility(status_=Facility.Status.APPROVED)
        self.applicant.facility = facility
        self.applicant.save()
        _auth(self.client, self.applicant)
        r = self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "already_assigned")

    def test_allows_resubmit_after_rejection(self):
        _auth(self.client, self.applicant)
        self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        rejected = Facility.objects.get(submitted_by=self.applicant)
        rejected.status = Facility.Status.REJECTED
        rejected.save()
        r = self.client.post(
            "/api/v1/facilities/applications/", self._valid_payload(), format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Listing & retrieving applications
# ---------------------------------------------------------------------------


class FacilityApplicationListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.applicant = _mk_user("appl", User.Role.HEALTH_WORKER)
        self.other = _mk_user("other", User.Role.HEALTH_WORKER)

        self.f1 = _mk_facility("One", Facility.Status.PENDING, submitted_by=self.applicant)
        self.f2 = _mk_facility("Two", Facility.Status.PENDING, submitted_by=self.other)
        self.f3 = _mk_facility("Three", Facility.Status.APPROVED)

    def test_admin_sees_pending_only(self):
        _auth(self.client, self.admin)
        r = self.client.get("/api/v1/facilities/applications/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = {x["id"] for x in r.data["results"]}
        self.assertEqual(ids, {self.f1.id, self.f2.id})

    def test_coordinator_sees_pending(self):
        _auth(self.client, self.coord)
        r = self.client.get("/api/v1/facilities/applications/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_facility_user_cannot_list(self):
        _auth(self.client, self.applicant)
        r = self.client.get("/api/v1/facilities/applications/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_submitter_can_retrieve_own(self):
        _auth(self.client, self.applicant)
        r = self.client.get(f"/api/v1/facilities/applications/{self.f1.id}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["id"], self.f1.id)

    def test_other_user_cannot_retrieve(self):
        _auth(self.client, self.applicant)
        r = self.client.get(f"/api/v1/facilities/applications/{self.f2.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_retrieve_any(self):
        _auth(self.client, self.admin)
        r = self.client.get(f"/api/v1/facilities/applications/{self.f1.id}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Approve / reject
# ---------------------------------------------------------------------------


class FacilityApproveTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.applicant = _mk_user("appl", User.Role.HEALTH_WORKER)
        self.facility = _mk_facility(
            "F", Facility.Status.PENDING, submitted_by=self.applicant
        )

    def test_non_central_cannot_approve(self):
        _auth(self.client, self.applicant)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_approves(self):
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {"review_note": "Looks good"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.status, Facility.Status.APPROVED)
        self.assertEqual(self.facility.reviewed_by, self.admin)
        self.assertIsNotNone(self.facility.reviewed_at)
        self.assertEqual(self.facility.review_note, "Looks good")

    def test_coordinator_approves(self):
        _auth(self.client, self.coord)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_approve_promotes_submitter_to_manager(self):
        _auth(self.client, self.admin)
        self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {},
            format="json",
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.facility, self.facility)
        self.assertEqual(self.applicant.role, User.Role.FACILITY_MANAGER)

    def test_approve_does_not_override_existing_facility(self):
        other_fac = _mk_facility("Other", Facility.Status.APPROVED)
        self.applicant.facility = other_fac
        self.applicant.save()

        _auth(self.client, self.admin)
        self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {},
            format="json",
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.facility, other_fac)

    def test_approve_non_pending_returns_409(self):
        self.facility.status = Facility.Status.APPROVED
        self.facility.save()
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r.data["code"], "invalid_state")

    def test_approve_creates_audit_log(self):
        _auth(self.client, self.admin)
        self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/approve/",
            {"review_note": "ok"},
            format="json",
        )
        entry = AuditLog.objects.get(action="FACILITY_APPROVED")
        self.assertEqual(entry.entity_type, "Facility")
        self.assertEqual(entry.entity_id, str(self.facility.id))
        self.assertEqual(entry.actor, self.admin)


class FacilityRejectTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.applicant = _mk_user("appl", User.Role.HEALTH_WORKER)
        self.facility = _mk_facility(
            "F", Facility.Status.PENDING, submitted_by=self.applicant
        )

    def test_reject_requires_note(self):
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/reject/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_succeeds(self):
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/reject/",
            {"review_note": "Incomplete documents"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.status, Facility.Status.REJECTED)
        self.assertEqual(self.facility.review_note, "Incomplete documents")
        self.assertTrue(
            AuditLog.objects.filter(action="FACILITY_REJECTED").exists()
        )

    def test_reject_pending_only(self):
        self.facility.status = Facility.Status.REJECTED
        self.facility.save()
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/reject/",
            {"review_note": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_facility_user_cannot_reject(self):
        _auth(self.client, self.applicant)
        r = self.client.post(
            f"/api/v1/facilities/applications/{self.facility.id}/reject/",
            {"review_note": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Facility CRUD, suspend, map
# ---------------------------------------------------------------------------


class FacilitySuspendTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.manager = _mk_user("mgr", User.Role.FACILITY_MANAGER)
        self.facility = _mk_facility("F", Facility.Status.APPROVED)
        self.manager.facility = self.facility
        self.manager.save()

    def test_only_admin(self):
        _auth(self.client, self.manager)
        r = self.client.post(f"/api/v1/facilities/{self.facility.id}/suspend/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

        _auth(self.client, self.coord)
        r = self.client.post(f"/api/v1/facilities/{self.facility.id}/suspend/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_suspends(self):
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/{self.facility.id}/suspend/",
            {"review_note": "Compliance issue"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.status, Facility.Status.SUSPENDED)
        self.assertTrue(AuditLog.objects.filter(action="FACILITY_SUSPENDED").exists())

    def test_suspend_already_suspended(self):
        self.facility.status = Facility.Status.SUSPENDED
        self.facility.save()
        _auth(self.client, self.admin)
        r = self.client.post(f"/api/v1/facilities/{self.facility.id}/suspend/")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)


class FacilityScopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.manager = _mk_user("mgr", User.Role.FACILITY_MANAGER)
        self.f_a = _mk_facility("A", Facility.Status.APPROVED)
        self.f_b = _mk_facility("B", Facility.Status.APPROVED)
        self.manager.facility = self.f_a
        self.manager.save()

    def test_admin_lists_all(self):
        _auth(self.client, self.admin)
        r = self.client.get("/api/v1/facilities/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 2)

    def test_manager_sees_own_only(self):
        _auth(self.client, self.manager)
        r = self.client.get("/api/v1/facilities/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["id"], self.f_a.id)

    def test_manager_get_other_returns_404(self):
        _auth(self.client, self.manager)
        r = self.client.get(f"/api/v1/facilities/{self.f_b.id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_unscoped_user_sees_nothing(self):
        loose = _mk_user("loose", User.Role.HEALTH_WORKER)
        _auth(self.client, loose)
        r = self.client.get("/api/v1/facilities/")
        self.assertEqual(r.data["count"], 0)

    def test_admin_can_patch_any(self):
        _auth(self.client, self.admin)
        r = self.client.patch(
            f"/api/v1/facilities/{self.f_b.id}/",
            {"landmark": "Near church"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_manager_can_patch_own(self):
        _auth(self.client, self.manager)
        r = self.client.patch(
            f"/api/v1/facilities/{self.f_a.id}/",
            {"landmark": "New"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(AuditLog.objects.filter(action="FACILITY_UPDATED").exists())

    def test_manager_cannot_patch_other(self):
        _auth(self.client, self.manager)
        r = self.client.patch(
            f"/api/v1/facilities/{self.f_b.id}/",
            {"landmark": "Hacked"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_rejects_disallowed_fields(self):
        _auth(self.client, self.manager)
        r = self.client.patch(
            f"/api/v1/facilities/{self.f_a.id}/",
            {"status": "APPROVED", "facility_type": "HOSPITAL"},
            format="json",
        )
        # Unknown / read-only fields are silently ignored by DRF
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.f_a.refresh_from_db()
        self.assertEqual(self.f_a.facility_type, "CLINIC")


class FacilityMapTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = _mk_user("mgr", User.Role.FACILITY_MANAGER)
        self.fac = _mk_facility(
            "Home",
            Facility.Status.APPROVED,
            latitude="9.010",
            longitude="38.760",
        )
        self.manager.facility = self.fac
        self.manager.save()

        _mk_facility(
            "Coord",
            Facility.Status.APPROVED,
            latitude="9.020",
            longitude="38.770",
        )
        _mk_facility("NoCoords", Facility.Status.APPROVED)  # no lat/lon
        _mk_facility(
            "Pending",
            Facility.Status.PENDING,
            latitude="9.030",
            longitude="38.780",
        )
        _mk_facility(
            "Suspended",
            Facility.Status.SUSPENDED,
            latitude="9.040",
            longitude="38.790",
        )

    def test_requires_approved_facility_user(self):
        unapproved = _mk_user("u", User.Role.HEALTH_WORKER)
        _auth(self.client, unapproved)
        r = self.client.get("/api/v1/facilities/map/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_returns_only_approved_with_coords(self):
        _auth(self.client, self.manager)
        r = self.client.get("/api/v1/facilities/map/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in r.data}
        self.assertEqual(names, {"Home", "Coord"})

    def test_admin_can_view(self):
        admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        _auth(self.client, admin)
        r = self.client.get("/api/v1/facilities/map/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Facility user management
# ---------------------------------------------------------------------------


class FacilityUserManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.manager = _mk_user("mgr", User.Role.FACILITY_MANAGER)
        self.fac = _mk_facility("Home", Facility.Status.APPROVED)
        self.manager.facility = self.fac
        self.manager.save()

        self.other_fac = _mk_facility("Other", Facility.Status.APPROVED)
        self.other_mgr = _mk_user("omgr", User.Role.FACILITY_MANAGER, facility=self.other_fac)

    def _payload(self, username="newuser", role="PHARMACIST"):
        return {
            "username": username,
            "email": f"{username}@x.com",
            "password": "StrongPass123!",
            "role": role,
            "phone": "+251911000000",
        }

    def test_manager_lists_own_users(self):
        _auth(self.client, self.manager)
        r = self.client.get(f"/api/v1/facilities/{self.fac.id}/users/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 1)  # only manager

    def test_manager_creates_pharmacist(self):
        _auth(self.client, self.manager)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["role"], "PHARMACIST")
        self.assertEqual(r.data["facility"], self.fac.id)
        self.assertNotIn("password", r.data)
        self.assertTrue(
            AuditLog.objects.filter(action="FACILITY_USER_CREATED").exists()
        )

    def test_manager_cannot_create_manager(self):
        _auth(self.client, self.manager)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload(role="FACILITY_MANAGER"),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", r.data)

    def test_manager_cannot_create_system_admin(self):
        _auth(self.client, self.manager)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload(role="SYSTEM_ADMIN"),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_create_manager(self):
        _auth(self.client, self.admin)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload(username="mgr2", role="FACILITY_MANAGER"),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_other_manager_blocked(self):
        _auth(self.client, self.other_mgr)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_pharmacist_cannot_create(self):
        pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fac)
        _auth(self.client, pharm)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_username_rejected(self):
        _auth(self.client, self.manager)
        self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload("dup"),
            format="json",
        )
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload("dup"),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_email_rejected(self):
        _auth(self.client, self.manager)
        self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/",
            self._payload("u1"),
            format="json",
        )
        payload = self._payload("u2")
        payload["email"] = "u1@x.com"
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/", payload, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate(self):
        target = _mk_user("t", User.Role.PHARMACIST, facility=self.fac)
        _auth(self.client, self.manager)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/{target.id}/deactivate/"
        )
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(
            AuditLog.objects.filter(action="FACILITY_USER_DEACTIVATED").exists()
        )

    def test_cannot_deactivate_self(self):
        _auth(self.client, self.manager)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/{self.manager.id}/deactivate/"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_deactivate_user_at_other_facility(self):
        target = _mk_user("o", User.Role.PHARMACIST, facility=self.other_fac)
        _auth(self.client, self.manager)
        r = self.client.post(
            f"/api/v1/facilities/{self.fac.id}/users/{target.id}/deactivate/"
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)