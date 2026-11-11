from rest_framework.permissions import BasePermission
from .models import User


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role == User.Role.SYSTEM_ADMIN


class IsCentralCoordinator(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role == User.Role.CENTRAL_COORDINATOR


class IsCentralUser(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in {
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        }


class IsFacilityManager(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role == User.Role.FACILITY_MANAGER


class IsPharmacistOrInventory(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in {
            User.Role.PHARMACIST,
            User.Role.INVENTORY_STAFF,
            User.Role.PHARMACY_STAFF,
        }


class IsHealthWorker(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role == User.Role.HEALTH_WORKER


class IsApprovedFacilityUser(BasePermission):
    """Authenticated user with an APPROVED, active facility."""

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated or not u.facility_id:
            return False
        f = u.facility
        return f is not None and f.status == "APPROVED" and f.is_active