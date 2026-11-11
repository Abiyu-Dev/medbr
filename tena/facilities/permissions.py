from rest_framework.permissions import BasePermission

from accounts.models import User


class CanViewFacilityMap(BasePermission):
    """Admins, coordinators, or staff of an APPROVED active facility."""

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role in {User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR}:
            return True
        if u.facility_id and u.facility.status == "APPROVED" and u.facility.is_active:
            return True
        return False