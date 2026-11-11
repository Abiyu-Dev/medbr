from rest_framework.permissions import BasePermission

from accounts.models import User


FACILITY_VACCINATION_ROLES = {
    User.Role.FACILITY_MANAGER,
    User.Role.HEALTH_WORKER,
}


def _has_vaccination_facility(user):
    return bool(
        user.facility_id
        and user.facility.status == "APPROVED"
        and user.facility.is_active
        and user.facility.provides_vaccination_services
    )


class IsVaccinationFacilityUser(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role == User.Role.SYSTEM_ADMIN:
            return True
        return u.role in FACILITY_VACCINATION_ROLES and _has_vaccination_facility(u)


class IsHealthWorkerOrManager(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role == User.Role.SYSTEM_ADMIN:
            return True
        return u.role in FACILITY_VACCINATION_ROLES and _has_vaccination_facility(u)


class IsScheduleAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )


class CanReadSchedules(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated