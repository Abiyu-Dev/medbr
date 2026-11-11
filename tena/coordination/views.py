from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsCentralUser
from accounts.services import log_audit
from inventory.models import TransferRequest
from inventory.serializers import TransferRequestSerializer

from .models import (
    DeliveryCoordination,
    SourcingProposal,
    SupplyGapReport,
    SupplyRequest,
)
from .permissions import (
    CanCoordinateDeliveries,
    CanViewSupplyRequests,
    IsCentralForGaps,
    IsCentralForSourcing,
)
from .serializers import *
from .services import (
    SourcingError,
    approve_sourcing_proposal,
    cancel_supply_request,
    refresh_supply_gaps,
    reject_sourcing_proposal,
)
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

def _ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ---------------------------------------------------------------------------
# Delivery coordination (nested under a transfer)
# ---------------------------------------------------------------------------

@extend_schema(tags=["Coordination"])
class TransferDeliveryCoordinationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, CanCoordinateDeliveries]

    def _get_transfer(self):
        try:
            transfer = TransferRequest.objects.get(pk=self.kwargs["transfer_pk"])
        except TransferRequest.DoesNotExist:
            raise PermissionDenied("Transfer not found.")

        user = self.request.user
        if user.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR):
            return transfer
        if user.facility_id and user.facility_id in (
            transfer.source_facility_id,
            transfer.destination_facility_id,
        ):
            return transfer
        raise PermissionDenied("Not authorized for this transfer.")

    def get_queryset(self):
        transfer = self._get_transfer()
        return DeliveryCoordination.objects.filter(
            transfer_request=transfer
        ).select_related("coordinator")

    def get_serializer_class(self):
        if self.action == "create":
            return DeliveryCoordinationCreateSerializer
        return DeliveryCoordinationSerializer

    def create(self, request, *args, **kwargs):
        transfer = self._get_transfer()
        ser = DeliveryCoordinationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        entry = ser.save(
            transfer_request=transfer,
            coordinator=request.user,
            last_contacted_at=timezone.now(),
        )
        log_audit(
            request.user,
            "DELIVERY_COORDINATION_CREATED",
            "DeliveryCoordination",
            entry.id,
            metadata={
                "transfer_id": transfer.id,
                "delivery_status": entry.delivery_status,
            },
            ip_address=_ip(request),
        )
        return Response(
            DeliveryCoordinationSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Supply gap reports (central only)
# ---------------------------------------------------------------------------

@extend_schema(tags=["Coordination"])
class SupplyGapReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsCentralForGaps]
    queryset = SupplyGapReport.objects.select_related(
        "facility", "product", "assigned_to"
    )
    serializer_class = SupplyGapReportSerializer
    filterset_fields = (
        "status",
        "priority",
        "facility",
        "product",
        "assigned_to",
    )
    search_fields = ("reason_summary", "facility__name", "product__name")
    ordering_fields = ("created_at", "updated_at", "priority", "uncovered_quantity")
    ordering = ["priority", "-uncovered_quantity"]

    @extend_schema(tags=["Coordination"], responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"])
    def refresh(self, request):
        facility_id = request.query_params.get("facility")
        facility = None
        if facility_id:
            from facilities.models import Facility

            try:
                facility = Facility.objects.get(pk=int(facility_id))
            except (Facility.DoesNotExist, ValueError):
                return Response(
                    {"detail": "Facility not found.", "code": "facility_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            horizon_days = int(request.query_params.get("horizon_days", 30))
            usage_window_days = int(
                request.query_params.get("usage_window_days", 30)
            )
        except ValueError:
            return Response(
                {
                    "detail": "horizon_days and usage_window_days must be integers.",
                    "code": "invalid_query",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        created, updated = refresh_supply_gaps(
            facility=facility,
            horizon_days=horizon_days,
            usage_window_days=usage_window_days,
        )

        active = SupplyGapReport.objects.filter(
            status__in=SupplyGapReport.NON_TERMINAL_STATUSES
        ).order_by("priority", "-uncovered_quantity")

        return Response(
            {
                "created": created,
                "updated": updated,
                "active_count": active.count(),
                "gaps": SupplyGapReportSerializer(active, many=True).data,
            }
        )

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        gap = self.get_object()
        ser = SupplyGapAssignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            user = User.objects.get(pk=ser.validated_data["assigned_to"])
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found.", "code": "user_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not user.is_active:
            return Response(
                {"detail": "User is inactive.", "code": "user_inactive"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if gap.status in SupplyGapReport.TERMINAL_STATUSES:
            return Response(
                {
                    "detail": "Cannot assign a resolved/closed gap.",
                    "code": "invalid_state",
                },
                status=status.HTTP_409_CONFLICT,
            )

        gap.assigned_to = user
        gap.status = SupplyGapReport.Status.ASSIGNED
        if ser.validated_data.get("note"):
            gap.reason_summary = (
                gap.reason_summary
                + f"\nAssigned by {request.user.username}: "
                + ser.validated_data["note"]
            )
        gap.save()

        log_audit(
            request.user,
            "SUPPLY_GAP_ASSIGNED",
            "SupplyGapReport",
            gap.id,
            metadata={"assigned_to": user.id},
            ip_address=_ip(request),
        )
        return Response(SupplyGapReportSerializer(gap).data)

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        gap = self.get_object()
        if gap.status in SupplyGapReport.TERMINAL_STATUSES:
            return Response(
                {
                    "detail": "Cannot escalate a resolved/closed gap.",
                    "code": "invalid_state",
                },
                status=status.HTTP_409_CONFLICT,
            )
        if gap.status == SupplyGapReport.Status.ESCALATED:
            return Response(
                {"detail": "Already escalated.", "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )

        ser = SupplyGapEscalateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = ser.validated_data.get("note", "")
        if note:
            gap.reason_summary = gap.reason_summary + f"\nEscalated: {note}"

        gap.status = SupplyGapReport.Status.ESCALATED
        gap.save()
        log_audit(
            request.user,
            "SUPPLY_GAP_ESCALATED",
            "SupplyGapReport",
            gap.id,
            metadata={"note": note},
            ip_address=_ip(request),
        )
        return Response(SupplyGapReportSerializer(gap).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        gap = self.get_object()
        if gap.status in SupplyGapReport.TERMINAL_STATUSES:
            return Response(
                {"detail": "Already resolved/closed.", "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )
        ser = SupplyGapResolveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        gap.status = ser.validated_data["final_status"]
        gap.resolution_notes = ser.validated_data["resolution_notes"]
        gap.save()
        log_audit(
            request.user,
            "SUPPLY_GAP_RESOLVED",
            "SupplyGapReport",
            gap.id,
            metadata={"final_status": gap.status},
            ip_address=_ip(request),
        )
        return Response(SupplyGapReportSerializer(gap).data)


# ---------------------------------------------------------------------------
# Supply requests (facility -> central) and sourcing proposals
# ---------------------------------------------------------------------------

CENTRAL_ROLES = {User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR}


@extend_schema(tags=["Coordination"])
class SupplyRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, CanViewSupplyRequests]
    serializer_class = SupplyRequestSerializer
    filterset_fields = ("status", "facility", "product")
    ordering_fields = ("created_at", "status")
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = SupplyRequest.objects.select_related(
            "facility", "product", "requested_by"
        )
        if user.role in CENTRAL_ROLES:
            return qs
        return qs.filter(facility_id=user.facility_id)

    @extend_schema(tags=["Coordination"], responses={200: SupplyRequestSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        supply_request = self.get_object()
        user = request.user
        if user.role not in CENTRAL_ROLES and supply_request.facility_id != user.facility_id:
            raise PermissionDenied("You can only cancel your own facility's requests.")
        if supply_request.status not in (
            SupplyRequest.Status.OPEN,
            SupplyRequest.Status.PLANNED,
        ):
            return Response(
                {
                    "detail": f"Cannot cancel a request in status {supply_request.status}.",
                    "code": "invalid_state",
                },
                status=status.HTTP_409_CONFLICT,
            )

        ser = SupplyRequestCancelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            supply_request = cancel_supply_request(
                request=supply_request,
                cancelled_by=user,
                reason=ser.validated_data.get("reason", ""),
            )
        except SourcingError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )

        log_audit(
            user,
            "SUPPLY_REQUEST_CANCELLED",
            "SupplyRequest",
            supply_request.id,
            metadata={"reason": ser.validated_data.get("reason", "")},
            ip_address=_ip(request),
        )
        return Response(SupplyRequestSerializer(supply_request).data)


@extend_schema(tags=["Coordination"])
class SourcingProposalViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsCentralForSourcing]
    serializer_class = SourcingProposalSerializer
    filterset_fields = ("request", "status", "source_facility", "product")
    ordering_fields = ("created_at", "status")
    ordering = ["-created_at"]
    queryset = SourcingProposal.objects.select_related(
        "request", "request__facility", "source_facility", "product", "reviewed_by"
    )

    @extend_schema(tags=["Coordination"], responses={200: SourcingProposalSerializer})
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        proposal = self.get_object()
        ser = SourcingApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            proposal, transfer = approve_sourcing_proposal(
                proposal=proposal,
                reviewed_by=request.user,
                note=ser.validated_data.get("note", ""),
            )
        except SourcingError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )

        log_audit(
            request.user,
            "SOURCING_PROPOSAL_APPROVED",
            "SourcingProposal",
            proposal.id,
            metadata={"transfer_id": transfer.id, "request_id": proposal.request_id},
            ip_address=_ip(request),
        )
        return Response(SourcingProposalSerializer(proposal).data)

    @extend_schema(tags=["Coordination"], responses={200: SourcingProposalSerializer})
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        proposal = self.get_object()
        ser = SourcingRejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            proposal = reject_sourcing_proposal(
                proposal=proposal,
                reviewed_by=request.user,
                note=ser.validated_data["note"],
            )
        except SourcingError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )

        log_audit(
            request.user,
            "SOURCING_PROPOSAL_REJECTED",
            "SourcingProposal",
            proposal.id,
            metadata={"note": ser.validated_data["note"]},
            ip_address=_ip(request),
        )
        return Response(SourcingProposalSerializer(proposal).data)