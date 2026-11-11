from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import AuditLog, User
from .serializers import AuditLogSerializer
from drf_spectacular.utils import extend_schema

@extend_schema(tags=["Audit"])
class AuditLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only audit log. Scoping rules:
      * SYSTEM_ADMIN:           everything
      * CENTRAL_COORDINATOR:    operational logs, excluding patient-level PII
      * FACILITY_MANAGER:       own facility (actions by its staff + facility lifecycle)
      * everyone else:          own actions only
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AuditLogSerializer
    filterset_fields = ("action", "entity_type")
    search_fields = ("action", "entity_type", "entity_id")
    ordering_fields = ("created_at",)
    ordering = ("-created_at",)
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = AuditLog.objects.select_related("actor", "actor__facility")

        if user.role == User.Role.SYSTEM_ADMIN:
            return qs

        if user.role == User.Role.CENTRAL_COORDINATOR:
            return qs.exclude(
                entity_type__in=["Patient", "VaccinationRecord", "VaccineFollowUp"]
            )

        if user.role == User.Role.FACILITY_MANAGER and user.facility_id:
            return qs.filter(
                Q(actor__facility_id=user.facility_id)
                | Q(
                    entity_type="Facility",
                    entity_id=str(user.facility_id),
                )
            )

        return qs.filter(actor=user)