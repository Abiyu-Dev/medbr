from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import User, AuditLog
from facilities.models import Facility


class UserModelTests(TestCase):
    def test_create_user_with_role(self):
        u = User.objects.create_user(
            username="pharm1",
            password="Pass12345!",
            email="pharm1@x.com",
            role=User.Role.PHARMACIST,
        )
        self.assertEqual(u.role, User.Role.PHARMACIST)
        self.assertTrue(u.check_password("Pass12345!"))

    def test_create_superuser(self):
        u = User.objects.create_superuser(
            username="root", password="Pass12345!", email="root@x.com"
        )
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.is_staff)

    def test_email_must_be_unique(self):
        User.objects.create_user(username="a", password="x", email="dup@x.com")
        with self.assertRaises(Exception):
            User.objects.create_user(username="b", password="x", email="dup@x.com")

    def test_audit_log_creates(self):
        u = User.objects.create_user(username="a", password="x", email="a@x.com")
        AuditLog.objects.create(
            actor=u, action="TEST_ACTION", entity_type="User", entity_id=str(u.id)
        )
        self.assertEqual(AuditLog.objects.count(), 1)


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            password="TestPass123!",
            email="test@x.com",
            role=User.Role.PHARMACIST,
        )

    def test_token_obtain_success(self):
        r = self.client.post(
            "/api/v1/auth/token/",
            {"username": "testuser", "password": "TestPass123!"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_token_obtain_invalid(self):
        r = self.client.post(
            "/api/v1/auth/token/",
            {"username": "testuser", "password": "wrong"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_contains_role_and_facility(self):
        import jwt

        r = self.client.post(
            "/api/v1/auth/token/",
            {"username": "testuser", "password": "TestPass123!"},
            format="json",
        )
        payload = jwt.decode(r.data["access"], options={"verify_signature": False})
        self.assertEqual(payload["role"], User.Role.PHARMACIST)
        self.assertIsNone(payload["facility_id"])

    def test_refresh_returns_new_access(self):
        r = self.client.post(
            "/api/v1/auth/token/",
            {"username": "testuser", "password": "TestPass123!"},
            format="json",
        )
        refresh = r.data["refresh"]
        r2 = self.client.post(
            "/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertIn("access", r2.data)

    def test_me_requires_auth(self):
        r = self.client.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_profile(self):
        self.client.force_authenticate(self.user)
        r = self.client.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["username"], "testuser")
        self.assertEqual(r.data["role"], User.Role.PHARMACIST)
        self.assertIsNone(r.data["facility"])

    def test_me_with_facility(self):
        fac = Facility.objects.create(
            name="Clinic A",
            facility_type=Facility.FacilityType.CLINIC,
            region="Addis Ababa",
            status=Facility.Status.APPROVED,
        )
        self.user.facility = fac
        self.user.save()
        self.client.force_authenticate(self.user)
        r = self.client.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["facility"], fac.id)
        self.assertEqual(r.data["facility_name"], "Clinic A")
        self.assertEqual(r.data["facility_status"], "APPROVED")


class PermissionClassTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory

        self.factory = APIRequestFactory()

    def _user(self, role, facility=None):
        username = f"u{role}_{facility.id if facility else 'none'}"

        return User.objects.create_user(
            username=username,
            email=f"{username}@test.com",
            password="testpass123",
            role=role,
            facility=facility,
        )

    def test_system_admin_only(self):
        from accounts.permissions import IsSystemAdmin
        from rest_framework.views import APIView

        view = APIView()
        req = self.factory.get("/")
        req.user = self._user(User.Role.SYSTEM_ADMIN)
        self.assertTrue(IsSystemAdmin().has_permission(req, view))

        req.user = self._user(User.Role.PHARMACIST)
        self.assertFalse(IsSystemAdmin().has_permission(req, view))

    def test_is_approved_facility_user(self):
        from accounts.permissions import IsApprovedFacilityUser
        from rest_framework.views import APIView

        approved = Facility.objects.create(
            name="A", facility_type="CLINIC", region="X", status="APPROVED"
        )
        pending = Facility.objects.create(
            name="B", facility_type="CLINIC", region="X", status="PENDING"
        )
        view = APIView()

        u_ok = self._user(User.Role.PHARMACIST, facility=approved)
        req = self.factory.get("/")
        req.user = u_ok
        self.assertTrue(IsApprovedFacilityUser().has_permission(req, view))

        u_pending = self._user(User.Role.PHARMACIST, facility=pending)
        req.user = u_pending
        self.assertFalse(IsApprovedFacilityUser().has_permission(req, view))

        u_none = self._user(User.Role.PHARMACIST, facility=None)
        req.user = u_none
        self.assertFalse(IsApprovedFacilityUser().has_permission(req, view))