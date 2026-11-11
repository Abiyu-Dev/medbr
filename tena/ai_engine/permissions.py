from rest_framework.permissions import BasePermission

from accounts.models import User

CENTRAL_ROLES = {User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR}
RUN_INVENTORY_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.CENTRAL_COORDINATOR,
    User.Role.FACILITY_MANAGER,
    User.Role.PHARMACIST,
}
REVIEW_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.CENTRAL_COORDINATOR,
    User.Role.FACILITY_MANAGER,
}


class CanRunInventoryAnalysis(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in RUN_INVENTORY_ROLES


class CanRunGapPrioritization(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in CENTRAL_ROLES


class CanRunTransferSourcing(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in CENTRAL_ROLES


class CanRunVaccinationDemand(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role in CENTRAL_ROLES:
            return True
        if u.role == User.Role.HEALTH_WORKER:
            return bool(
                u.facility_id
                and u.facility.status == "APPROVED"
                and u.facility.is_active
                and u.facility.provides_vaccination_services
            )
        return False


class CanReviewRecommendation(BasePermission):
    """Approval authority is checked per-object in the view."""

    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in REVIEW_ROLES