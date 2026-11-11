from rest_framework.permissions import BasePermission

from accounts.models import User


def _has_approved_facility(user):
    return bool(
        user.facility_id
        and user.facility.status == "APPROVED"
        and user.facility.is_active
    )


class CanManageStock(BasePermission):
    """Receipts, consumption, wastage, batch status changes."""

    ROLES = {
        User.Role.FACILITY_MANAGER,
        User.Role.PHARMACIST,
        User.Role.INVENTORY_STAFF,
        User.Role.PHARMACY_STAFF,
    }

    def has_permission(self, request, view):
        u = request.user

        if not u.is_authenticated:
            return False

        if u.role == User.Role.SYSTEM_ADMIN:
            return True

        if u.role not in self.ROLES:
            return False

        # Allow the view to return the specific no_facility response.
        if not u.facility_id:
            return True

        return _has_approved_facility(u)


class CanAdjustStock(BasePermission):
    """Elevated corrections: facility manager (own) or system admin."""

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role == User.Role.SYSTEM_ADMIN:
            return True
        return u.role == User.Role.FACILITY_MANAGER and _has_approved_facility(u)