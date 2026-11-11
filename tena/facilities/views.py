from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsCentralUser, IsSystemAdmin
from accounts.serializers import UserCreateSerializer, UserSerializer
from accounts.services import log_audit

from .models import Facility
from .permissions import CanViewFacilityMap
from .serializers import *
from drf_spectacular.utils import extend_schema

def _ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _is_central(user):
    return user.role in {User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR}


def _scope_facilities(user, qs):
    if _is_central(user):
        return qs
    if user.facility_id:
        return qs.filter(id=user.facility_id)
    return qs.none()


# ---------------------------------------------------------------------------
# Facility applications (submission + central review queue)
# ---------------------------------------------------------------------------

@extend_schema(tags=["Facilities"])
class FacilityApplicationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    queryset = Facility.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return FacilityApplicationCreateSerializer
        return FacilitySerializer

    def get_queryset(self):
        user = self.request.user
        base = Facility.objects.all()
        if self.action == "list":
            if not _is_central(user):
                raise PermissionDenied("Only central users can list applications.")
            return base.filter(status=Facility.Status.PENDING)
        if self.action == "retrieve":
            if _is_central(user):
                return base
            return base.filter(submitted_by=user)
        if self.action in ("approve", "reject"):
            return base
        return base.none()

    # --- POST /facilities/applications/ ---
    def create(self, request, *args, **kwargs):
        user = request.user
        if user.facility_id:
            return Response(
                {
                    "detail": "You are already assigned to a facility.",
                    "code": "already_assigned",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        has_active_submission = Facility.objects.filter(
            submitted_by=user,
            status__in=[Facility.Status.PENDING, Facility.Status.APPROVED],
        ).exists()
        if has_active_submission:
            return Response(
                {
                    "detail": "You already have a pending or approved application.",
                    "code": "duplicate_application",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            facility = ser.save(
                status=Facility.Status.PENDING,
                submitted_by=user,
            )
            log_audit(
                user,
                "FACILITY_APPLICATION_SUBMITTED",
                "Facility",
                facility.id,
                metadata={"name": facility.name},
                ip_address=_ip(request),
            )
        return Response(
            FacilitySerializer(facility).data, status=status.HTTP_201_CREATED
        )

    # --- POST /facilities/applications/{id}/approve/ ---
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not _is_central(request.user):
            raise PermissionDenied("Only central users can approve applications.")
        facility = self.get_object()
        if facility.status != Facility.Status.PENDING:
            return Response(
                {
                    "detail": "Only PENDING applications can be approved.",
                    "code": "invalid_state",
                },
                status=status.HTTP_409_CONFLICT,
            )

        review_note = request.data.get("review_note", "") or ""
        with transaction.atomic():
            facility.status = Facility.Status.APPROVED
            facility.reviewed_by = request.user
            facility.reviewed_at = timezone.now()
            facility.review_note = review_note
            facility.save(
                update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
            )

            submitter = facility.submitted_by
            if submitter is not None and submitter.facility_id is None:
                submitter.facility = facility
                submitter.role = User.Role.FACILITY_MANAGER
                submitter.save(update_fields=["facility", "role"])

            log_audit(
                request.user,
                "FACILITY_APPROVED",
                "Facility",
                facility.id,
                metadata={"name": facility.name, "review_note": review_note},
                ip_address=_ip(request),
            )
        return Response(FacilitySerializer(facility).data)

    # --- POST /facilities/applications/{id}/reject/ ---
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        if not _is_central(request.user):
            raise PermissionDenied("Only central users can reject applications.")
        facility = self.get_object()
        if facility.status != Facility.Status.PENDING:
            return Response(
                {
                    "detail": "Only PENDING applications can be rejected.",
                    "code": "invalid_state",
                },
                status=status.HTTP_409_CONFLICT,
            )

        ser = FacilityRejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = ser.validated_data["review_note"]

        with transaction.atomic():
            facility.status = Facility.Status.REJECTED
            facility.reviewed_by = request.user
            facility.reviewed_at = timezone.now()
            facility.review_note = note
            facility.save(
                update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
            )
            log_audit(
                request.user,
                "FACILITY_REJECTED",
                "Facility",
                facility.id,
                metadata={"name": facility.name, "review_note": note},
                ip_address=_ip(request),
            )
        return Response(FacilitySerializer(facility).data)


# ---------------------------------------------------------------------------
# Facility CRUD, suspend, map
# ---------------------------------------------------------------------------

@extend_schema(tags=["Facilities"])
class FacilityViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_fields = ("status", "facility_type", "region", "has_cold_chain")
    search_fields = ("name", "region", "town", "registration_number")
    ordering_fields = ("name", "created_at", "status")

    def get_queryset(self):
        return _scope_facilities(self.request.user, Facility.objects.all())

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return FacilityUpdateSerializer
        return FacilitySerializer

    def update(self, request, *args, **kwargs):
        facility = self.get_object()
        user = request.user
        if user.role != User.Role.SYSTEM_ADMIN:
            if not (
                user.role == User.Role.FACILITY_MANAGER
                and user.facility_id == facility.id
            ):
                raise PermissionDenied(
                    "Only facility managers (own facility) or system admins can update."
                )
        if facility.status == Facility.Status.SUSPENDED:
            return Response(
                {"detail": "Suspended facilities cannot be edited.", "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )
        response = super().update(request, *args, **kwargs)
        log_audit(
            user,
            "FACILITY_UPDATED",
            "Facility",
            facility.id,
            metadata={"fields": list(request.data.keys())},
            ip_address=_ip(request),
        )
        return response

    # --- POST /facilities/{id}/suspend/ ---
    @action(detail=True, methods=["post"], permission_classes=[IsSystemAdmin])
    def suspend(self, request, pk=None):
        facility = self.get_object()
        if facility.status == Facility.Status.SUSPENDED:
            return Response(
                {"detail": "Facility is already suspended.", "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )
        ser = FacilitySuspendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = ser.validated_data.get("review_note", "")

        with transaction.atomic():
            facility.status = Facility.Status.SUSPENDED
            facility.reviewed_by = request.user
            facility.reviewed_at = timezone.now()
            facility.review_note = note
            facility.save(
                update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
            )
            log_audit(
                request.user,
                "FACILITY_SUSPENDED",
                "Facility",
                facility.id,
                metadata={"name": facility.name, "review_note": note},
                ip_address=_ip(request),
            )
        return Response(FacilitySerializer(facility).data)

    # --- GET /facilities/map/ ---
    @action(detail=False, methods=["get"], permission_classes=[CanViewFacilityMap])
    def map(self, request):
        qs = (
            Facility.objects.filter(status=Facility.Status.APPROVED, is_active=True)
            .exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
        )
        data = [
            {
                "id": f.id,
                "name": f.name,
                "facility_type": f.facility_type,
                "region": f.region,
                "latitude": str(f.latitude),
                "longitude": str(f.longitude),
            }
            for f in qs
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# Facility user management (nested under /facilities/{facility_pk}/users/)
# ---------------------------------------------------------------------------

@extend_schema(tags=["Facilities"])
class FacilityUserViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def _get_facility(self):
        try:
            facility = Facility.objects.get(pk=self.kwargs["facility_pk"])
        except Facility.DoesNotExist:
            raise NotFound("Facility not found.")
        user = self.request.user
        if user.role == User.Role.SYSTEM_ADMIN:
            return facility
        if user.role == User.Role.FACILITY_MANAGER and user.facility_id == facility.id:
            return facility
        raise PermissionDenied("Not authorized to manage this facility's users.")

    def get_queryset(self):
        facility = self._get_facility()
        return User.objects.filter(facility=facility).order_by("id")

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        facility = self._get_facility()
        ser = UserCreateSerializer(
            data=request.data,
            context={"request": request, "facility": facility},
        )
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            user = ser.save()
            log_audit(
                request.user,
                "FACILITY_USER_CREATED",
                "User",
                user.id,
                metadata={"facility_id": facility.id, "role": user.role},
                ip_address=_ip(request),
            )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    # --- POST /facilities/{facility_pk}/users/{pk}/deactivate/ ---
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None, **kwargs):
        facility = self._get_facility()
        try:
            target = User.objects.get(pk=pk, facility=facility)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found at this facility."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if target.id == request.user.id:
            return Response(
                {"detail": "You cannot deactivate yourself.", "code": "invalid_state"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not target.is_active:
            return Response(
                {"detail": "User is already inactive.", "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )
        target.is_active = False
        target.save(update_fields=["is_active"])
        log_audit(
            request.user,
            "FACILITY_USER_DEACTIVATED",
            "User",
            target.id,
            metadata={"facility_id": facility.id},
            ip_address=_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)