from rest_framework.permissions import BasePermission

from accounts.models import User


class CanCoordinateDeliveries(BasePermission):
    """Central users OR any staff of the two facilities on the transfer."""

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR):
            return True
        return u.role in {
            User.Role.FACILITY_MANAGER,
            User.Role.PHARMACIST,
            User.Role.INVENTORY_STAFF,
            User.Role.PHARMACY_STAFF,
        }


class IsCentralForGaps(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in {
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        }


class CanViewSupplyRequests(BasePermission):
    """Central users see all; facility staff see their own facility's."""

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role in {User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR}:
            return True
        return bool(u.facility_id)


class IsCentralForSourcing(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in {
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        }