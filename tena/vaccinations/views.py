from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.services import log_audit
from inventory.models import Product

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from .models import Patient, VaccinationRecord, VaccineFollowUp, VaccineSchedule
from .permissions import *
from .serializers import *
from .services import *


def _ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _err(exc, code="vaccination_error"):
    return Response(
        {"detail": str(exc), "code": code},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _next_patient_number(facility, attempt=0):
    count = Patient.objects.filter(facility=facility).count()
    suffix = f"-{attempt}" if attempt > 0 else ""
    return f"P-{facility.id:03d}-{count + 1:06d}{suffix}"


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

@extend_schema(tags=["Vaccinations"])
class PatientViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsVaccinationFacilityUser]
    filterset_fields = ("active", "sex")
    search_fields = ("patient_number", "full_name", "guardian_name", "patient_phone")
    ordering_fields = ("full_name", "created_at", "date_of_birth")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = Patient.objects.select_related("facility")
        if user.role == User.Role.SYSTEM_ADMIN:
            return qs
        if user.facility_id:
            return qs.filter(facility_id=user.facility_id)
        return qs.none()

    def get_serializer_class(self):
        if self.action == "create":
            return PatientCreateSerializer
        if self.action in ("update", "partial_update"):
            return PatientUpdateSerializer
        return PatientSerializer

    def create(self, request, *args, **kwargs):
        user = request.user
        facility = user.facility
        if facility is None:
            return Response(
                {"detail": "No facility assigned.", "code": "no_facility"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = PatientCreateSerializer(
            data=request.data, context={"request": request, "facility": facility}
        )
        ser.is_valid(raise_exception=True)

        patient_number = ser.validated_data.get("patient_number") or ""
        if not patient_number:
            for attempt in range(5):
                try:
                    with transaction.atomic():
                        patient = Patient.objects.create(
                            facility=facility,
                            patient_number=_next_patient_number(facility, attempt),
                            created_by=user,
                            **{
                                k: v
                                for k, v in ser.validated_data.items()
                                if k != "patient_number"
                            },
                        )
                        break
                except IntegrityError:
                    if attempt == 4:
                        raise
            else:  # pragma: no cover
                return Response(
                    {
                        "detail": "Could not generate a unique patient number.",
                        "code": "number_generation_failed",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            patient = Patient.objects.create(
                facility=facility,
                created_by=user,
                **ser.validated_data,
            )

        log_audit(
            user,
            "PATIENT_CREATED",
            "Patient",
            patient.id,
            metadata={"facility_id": facility.id},
            ip_address=_ip(request),
        )
        return Response(
            PatientSerializer(patient).data, status=status.HTTP_201_CREATED
        )


# ---------------------------------------------------------------------------
# Vaccines list (products filtered to category=VACCINE)
# ---------------------------------------------------------------------------

@extend_schema(tags=["Vaccinations"], responses={200: OpenApiTypes.OBJECT})
class VaccinesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Product.objects.filter(category=Product.Category.VACCINE, active=True)
        rows = [
            {
                "id": p.id,
                "name": p.name,
                "generic_name": p.generic_name,
                "unit_of_measure": p.unit_of_measure,
                "requires_cold_chain": p.requires_cold_chain,
                "description": p.description,
            }
            for p in qs.order_by("name")
        ]
        return Response(rows)


# ---------------------------------------------------------------------------
# Vaccine schedules
# ---------------------------------------------------------------------------

@extend_schema(tags=["Vaccinations"])
class VaccineScheduleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = VaccineSchedule.objects.select_related(
        "vaccine_product", "approved_by"
    )
    filterset_fields = ("vaccine_product", "dose_number", "active")
    search_fields = ("vaccine_product__name", "source_name")
    ordering_fields = ("dose_number", "effective_from", "created_at")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsAuthenticated(), IsScheduleAdmin()]
        return [IsAuthenticated(), CanReadSchedules()]

    def get_serializer_class(self):
        if self.action == "create":
            return VaccineScheduleCreateSerializer
        return VaccineScheduleSerializer

    def create(self, request, *args, **kwargs):
        ser = VaccineScheduleCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            # Supersede any existing active version for the same (product, dose)
            existing = (
                VaccineSchedule.objects.select_for_update()
                .filter(
                    vaccine_product=ser.validated_data["vaccine_product"],
                    dose_number=ser.validated_data["dose_number"],
                    active=True,
                )
                .first()
            )
            if existing is not None and ser.validated_data.get("active", True):
                existing.active = False
                existing.save(update_fields=["active", "updated_at"])

            schedule = ser.save(approved_by=request.user)

        log_audit(
            request.user,
            "VACCINE_SCHEDULE_CREATED",
            "VaccineSchedule",
            schedule.id,
            metadata={
                "product_id": schedule.vaccine_product_id,
                "dose_number": schedule.dose_number,
            },
            ip_address=_ip(request),
        )
        return Response(
            VaccineScheduleSerializer(schedule).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Vaccination records
# ---------------------------------------------------------------------------

@extend_schema(tags=["Vaccinations"])
class VaccinationRecordViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsHealthWorkerOrManager]
    filterset_fields = ("patient", "vaccine_product", "dose_number", "facility")
    search_fields = ("patient__full_name", "patient__patient_number", "vaccine_product__name")
    ordering_fields = ("administered_at", "created_at")
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = VaccinationRecord.objects.select_related(
            "patient", "vaccine_product", "batch", "facility", "recorded_by", "schedule"
        )
        if user.role == User.Role.SYSTEM_ADMIN:
            return qs
        if user.facility_id:
            return qs.filter(facility_id=user.facility_id)
        return qs.none()

    def get_serializer_class(self):
        if self.action == "create":
            return VaccinationRecordCreateSerializer
        return VaccinationRecordSerializer

    def create(self, request, *args, **kwargs):
        user = request.user
        if user.facility is None:
            return Response(
                {"detail": "No facility assigned.", "code": "no_facility"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = VaccinationRecordCreateSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)

        try:
            record, next_follow_up = record_vaccination(
                patient=ser.validated_data["patient"],
                vaccine_product=ser.validated_data["vaccine_product"],
                dose_number=ser.validated_data["dose_number"],
                administered_at=ser.validated_data["administered_at"],
                facility=user.facility,
                batch=ser.validated_data["batch"],
                recorded_by=user,
                notes=ser.validated_data.get("notes", ""),
            )
        except VaccinationError as exc:
            return _err(exc)

        log_audit(
            user,
            "VACCINATION_RECORDED",
            "VaccinationRecord",
            record.id,
            metadata={
                "patient_id": record.patient_id,
                "product_id": record.vaccine_product_id,
                "dose_number": record.dose_number,
            },
            ip_address=_ip(request),
        )

        body = {
            "record": VaccinationRecordSerializer(record).data,
            "next_follow_up": (
                VaccineFollowUpSerializer(next_follow_up).data
                if next_follow_up
                else None
            ),
        }
        return Response(body, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------

@extend_schema(tags=["Vaccinations"])
class VaccineFollowUpViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsHealthWorkerOrManager]
    filterset_fields = ("status", "vaccine_product", "patient", "dose_number", "assigned_to")
    search_fields = ("patient__full_name", "patient__patient_number", "vaccine_product__name")
    ordering_fields = ("due_date", "created_at", "status")
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        facility = user.facility
        if facility is not None:
            sync_follow_up_statuses(facility)

        qs = VaccineFollowUp.objects.select_related(
            "patient", "patient__facility", "vaccine_product", "assigned_to"
        )
        if user.role == User.Role.SYSTEM_ADMIN:
            return qs
        if user.facility_id:
            return qs.filter(patient__facility_id=user.facility_id)
        return qs.none()

    def get_serializer_class(self):
        if self.action == "create":
            return VaccineFollowUpCreateSerializer
        return VaccineFollowUpSerializer

    def create(self, request, *args, **kwargs):
        ser = VaccineFollowUpCreateSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)

        assigned_to = None
        if ser.validated_data.get("assigned_to"):
            try:
                assigned_to = User.objects.get(pk=ser.validated_data["assigned_to"])
            except User.DoesNotExist:
                return Response(
                    {"detail": "Assigned user not found.", "code": "user_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            follow_up = create_follow_up(
                patient=ser.validated_data["patient"],
                vaccine_product=ser.validated_data["vaccine_product"],
                dose_number=ser.validated_data["dose_number"],
                due_date=ser.validated_data["due_date"],
                assigned_to=assigned_to,
                created_by=request.user,
            )
        except VaccinationError as exc:
            return _err(exc)

        return Response(
            VaccineFollowUpSerializer(follow_up).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def contact(self, request, pk=None):
        follow_up = self.get_object()
        ser = ContactFollowUpSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            follow_up = record_contact(
                follow_up=follow_up,
                outcome=ser.validated_data["outcome"],
                notes=ser.validated_data.get("notes", ""),
                next_action_date=ser.validated_data.get("next_action_date"),
                performed_by=request.user,
            )
        except VaccinationError as exc:
            return _err(exc)

        log_audit(
            request.user,
            "FOLLOW_UP_CONTACT_RECORDED",
            "VaccineFollowUp",
            follow_up.id,
            metadata={"outcome": follow_up.contact_outcome},
            ip_address=_ip(request),
        )
        return Response(VaccineFollowUpSerializer(follow_up).data)

    @action(detail=True, methods=["post"], url_path="mark-review-required")
    def mark_review_required(self, request, pk=None):
        follow_up = self.get_object()
        ser = MarkReviewRequiredSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            follow_up = mark_review_required(
                follow_up=follow_up,
                reason=ser.validated_data["reason"],
                performed_by=request.user,
            )
        except VaccinationError as exc:
            return _err(exc)

        log_audit(
            request.user,
            "FOLLOW_UP_REVIEW_REQUIRED",
            "VaccineFollowUp",
            follow_up.id,
            metadata={"reason": follow_up.review_reason},
            ip_address=_ip(request),
        )
        return Response(VaccineFollowUpSerializer(follow_up).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        follow_up = self.get_object()
        ser = CancelFollowUpSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            follow_up = cancel_follow_up(
                follow_up=follow_up,
                reason=ser.validated_data.get("reason", ""),
                performed_by=request.user,
            )
        except VaccinationError as exc:
            return _err(exc)

        log_audit(
            request.user,
            "FOLLOW_UP_CANCELLED",
            "VaccineFollowUp",
            follow_up.id,
            metadata={"reason": ser.validated_data.get("reason", "")},
            ip_address=_ip(request),
        )
        return Response(VaccineFollowUpSerializer(follow_up).data)


# ---------------------------------------------------------------------------
# Due / Overdue lists
# ---------------------------------------------------------------------------

@extend_schema(tags=["Vaccinations"])
class _FollowUpListBase(APIView):
    permission_classes = [IsAuthenticated, IsVaccinationFacilityUser]
    window_days = 7

    def _respond(self, request, today):
        user = request.user
        facility = user.facility
        if facility is None:
            return Response(
                {"detail": "No facility assigned.", "code": "no_facility"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sync_follow_up_statuses(facility, today=today)
        return facility

    def _base_queryset(self, facility):
        return VaccineFollowUp.objects.filter(
            patient__facility=facility,
            patient__active=True,
        ).select_related("patient", "vaccine_product", "assigned_to")


@extend_schema(tags=["Vaccinations"], responses={200: OpenApiTypes.OBJECT})
class DueFollowUpsView(_FollowUpListBase):
    def get(self, request):
        today = timezone.localdate()
        facility = self._respond(request, today)
        if not hasattr(facility, "id"):
            return facility

        horizon = today + timedelta(days=self.window_days)
        qs = (
            self._base_queryset(facility)
            .filter(
                due_date__gte=today,
                due_date__lte=horizon,
                status__in=[VaccineFollowUp.Status.UPCOMING, VaccineFollowUp.Status.DUE],
            )
            .order_by("due_date", "patient__full_name")
        )
        return Response(
            {
                "as_of": today,
                "window_days": self.window_days,
                "count": qs.count(),
                "follow_ups": VaccineFollowUpSerializer(qs, many=True).data,
            }
        )

@extend_schema(tags=["Vaccinations"], responses={200: OpenApiTypes.OBJECT})
class OverdueFollowUpsView(_FollowUpListBase):
    def get(self, request):
        today = timezone.localdate()
        facility = self._respond(request, today)
        if not hasattr(facility, "id"):
            return facility

        qs = (
            self._base_queryset(facility)
            .filter(
                due_date__lt=today,
                status__in=[
                    VaccineFollowUp.Status.UPCOMING,
                    VaccineFollowUp.Status.DUE,
                    VaccineFollowUp.Status.OVERDUE,
                    VaccineFollowUp.Status.CONTACT_ATTEMPTED,
                ],
            )
            .order_by("due_date", "patient__full_name")
        )
        return Response(
            {
                "as_of": today,
                "count": qs.count(),
                "follow_ups": VaccineFollowUpSerializer(qs, many=True).data,
            }
        )