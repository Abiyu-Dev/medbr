from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsSystemAdmin
from accounts.services import log_audit

from .models import *
from .permissions import *
from .serializers import *
from .services import *

from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from facilities.models import Facility

from .calculations import *

from accounts.models import User as _User
from django.db import models
from .transfers import *
from drf_spectacular.utils import extend_schema

def _ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _stock_error_response(exc):
    return Response(
        {"detail": str(exc), "code": "stock_error"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _facility_required_response():
    return Response(
        {
            "detail": "You must be assigned to an approved facility to perform this action.",
            "code": "no_facility",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _has_approved_facility(user):
    return bool(
        user.facility_id
        and user.facility.status == "APPROVED"
        and user.facility.is_active
    )


# ----------------------------- Products -----------------------------

@extend_schema(tags=["Inventory"])
class ProductViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_fields = ("category", "active", "requires_cold_chain")
    search_fields = ("name", "generic_name")
    ordering_fields = ("name", "category", "created_at")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsSystemAdmin()]
        return [IsAuthenticated()]


# ----------------------------- Batches -----------------------------

@extend_schema(tags=["Inventory"])
class StockBatchViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    filterset_fields = ("product", "storage_status", "facility")
    search_fields = ("batch_number", "product__name")
    ordering_fields = ("expiry_date", "quantity_available", "received_at")
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return StockBatchUpdateSerializer
        return StockBatchSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update"):
            return [CanManageStock()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = StockBatch.objects.select_related("facility", "product")
        if user.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR):
            return qs
        if user.facility_id:
            return qs.filter(facility_id=user.facility_id)
        return qs.none()

    def perform_update(self, serializer):
        instance = self.get_object()
        old_status = instance.storage_status
        instance = serializer.save()
        if old_status != instance.storage_status:
            log_audit(
                self.request.user,
                "BATCH_STORAGE_STATUS_CHANGED",
                "StockBatch",
                instance.id,
                metadata={
                    "from": old_status,
                    "to": instance.storage_status,
                    "batch_number": instance.batch_number,
                },
                ip_address=_ip(self.request),
            )


# ----------------------------- Movements (read-only) -----------------------------

@extend_schema(tags=["Inventory"])
class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    filterset_fields = ("batch", "movement_type", "direction")
    search_fields = ("batch__batch_number", "batch__product__name", "reason")
    ordering_fields = ("created_at", "occurred_at", "quantity")

    def get_queryset(self):
        user = self.request.user
        qs = StockMovement.objects.select_related(
            "batch", "batch__product", "batch__facility", "performed_by"
        )
        if user.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR):
            return qs
        if user.facility_id:
            return qs.filter(batch__facility_id=user.facility_id)
        return qs.none()


# ----------------------------- Action endpoints -----------------------------

@extend_schema(tags=["Inventory"])
class StockReceiptView(APIView):
    permission_classes = [IsAuthenticated, CanManageStock]

    def post(self, request):
        user = request.user
        facility = user.facility
        if facility is None:
            return _facility_required_response()

        if not _has_approved_facility(user) and user.role != User.Role.SYSTEM_ADMIN:
            return _facility_required_response()

        

        ser = StockReceiptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        facility = user.facility
        if facility is None:
            return _facility_required_response()

        try:
            batch, movement, created = receive_stock(
                facility=facility,
                product=ser.validated_data["product"],
                batch_number=ser.validated_data["batch_number"],
                expiry_date=ser.validated_data["expiry_date"],
                quantity=ser.validated_data["quantity"],
                source_reference=ser.validated_data.get("source_reference", ""),
                performed_by=user,
                idempotency_key=ser.validated_data.get("idempotency_key"),
            )
        except StockError as exc:
            return _stock_error_response(exc)

        body = {
            "batch": StockBatchSerializer(batch).data,
            "movement": StockMovementSerializer(movement).data,
            "replayed": not created,
        }
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

@extend_schema(tags=["Inventory"])
class StockConsumptionView(APIView):
    permission_classes = [IsAuthenticated, CanManageStock]

    def post(self, request):
        ser = StockConsumptionSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)

        try:
            movement, created = consume_stock(
                batch=ser.validated_data["batch"],
                quantity=ser.validated_data["quantity"],
                performed_by=request.user,
                reason=ser.validated_data.get("reason", ""),
                reference_type=ser.validated_data.get("reference_type", ""),
                reference_id=ser.validated_data.get("reference_id", ""),
                idempotency_key=ser.validated_data.get("idempotency_key"),
            )
        except StockError as exc:
            return _stock_error_response(exc)

        return Response(
            {
                "movement": StockMovementSerializer(movement).data,
                "replayed": not created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

@extend_schema(tags=["Inventory"])
class StockWastageView(APIView):
    permission_classes = [IsAuthenticated, CanManageStock]

    def post(self, request):
        ser = StockWastageSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        try:
            movement, created = record_wastage(
                batch=ser.validated_data["batch"],
                quantity=ser.validated_data["quantity"],
                reason=ser.validated_data["reason"],
                performed_by=request.user,
                idempotency_key=ser.validated_data.get("idempotency_key"),
            )
        except StockError as exc:
            return _stock_error_response(exc)

        return Response(
            {
                "movement": StockMovementSerializer(movement).data,
                "replayed": not created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

@extend_schema(tags=["Inventory"])
class StockAdjustmentView(APIView):
    permission_classes = [IsAuthenticated, CanAdjustStock]

    def post(self, request):
        ser = StockAdjustmentSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)

        user = request.user
        if user.role != User.Role.SYSTEM_ADMIN and not _has_approved_facility(user):
            return _facility_required_response()

        try:
            movement, created = adjust_stock(
                batch=ser.validated_data["batch"],
                quantity=ser.validated_data["quantity"],
                direction=ser.validated_data["direction"],
                reason=ser.validated_data["reason"],
                performed_by=user,
                idempotency_key=ser.validated_data.get("idempotency_key"),
            )
        except StockError as exc:
            return _stock_error_response(exc)

        # Adjustments are the one stock operation extra-audited outside the ledger,
        # because they bypass physical intake and deserve a named reviewer trail.
        log_audit(
            user,
            "STOCK_ADJUSTED",
            "StockMovement",
            movement.id,
            metadata={
                "batch_id": movement.batch_id,
                "direction": movement.direction,
                "quantity": movement.quantity,
                "reason": movement.reason,
            },
            ip_address=_ip(request),
        )

        return Response(
            {
                "movement": StockMovementSerializer(movement).data,
                "replayed": not created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )



# ----------------------------- Equipment -----------------------------

@extend_schema(tags=["Inventory"])
class EquipmentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    filterset_fields = ("facility", "condition", "category")
    search_fields = ("name", "asset_identifier")
    ordering_fields = ("name", "created_at", "condition")

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return EquipmentUpdateSerializer
        return EquipmentSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [CanManageStock()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Equipment.objects.select_related("facility", "created_by")
        if user.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR):
            return qs
        if user.facility_id:
            return qs.filter(facility_id=user.facility_id)
        return qs.none()

    def create(self, request, *args, **kwargs):
        user = request.user
        data = {**request.data}
        if user.role != User.Role.SYSTEM_ADMIN:
            if not _has_approved_facility(user):
                return _facility_required_response()
            data["facility"] = user.facility_id
        ser = EquipmentSerializer(data=data)
        ser.is_valid(raise_exception=True)
        # Only admins can create equipment for an arbitrary facility;
        # enforce that the target facility exists and is active.
        target = ser.validated_data["facility"]
        if not target.is_active:
            return Response(
                {"detail": "Target facility is inactive.", "code": "facility_inactive"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = ser.save(created_by=user)
        return Response(
            EquipmentSerializer(instance).data, status=status.HTTP_201_CREATED
        )


# ----------------------------- Inventory rollups -----------------------------


def _resolve_facility(request):
    """
    Returns (facility, None) or (None, Response).
    Facility users: own facility only (mismatched ?facility= is 403).
    Central users: must pass ?facility=<id>.
    """
    user = request.user
    central = user.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR)
    param = request.query_params.get("facility")

    if central:
        if not param:
            return None, Response(
                {
                    "detail": "facility query parameter is required for central users.",
                    "code": "facility_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            fac = Facility.objects.get(pk=int(param))
        except (Facility.DoesNotExist, ValueError):
            return None, Response(
                {"detail": "Facility not found.", "code": "facility_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return fac, None

    if not user.facility_id:
        return None, Response(
            {"detail": "You are not assigned to a facility.", "code": "no_facility"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if param and int(param) != user.facility_id:
        return None, Response(
            {
                "detail": "You cannot access another facility's inventory.",
                "code": "forbidden",
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if user.facility.status != Facility.Status.APPROVED or not user.facility.is_active:
        return None, Response(
            {
                "detail": "Your facility is not approved or is inactive.",
                "code": "facility_inactive",
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return user.facility, None


def _parse_int(query, name, default, minimum=1):
    raw = query.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer.")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return value

@extend_schema(tags=["Inventory"])
class InventorySummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility, err = _resolve_facility(request)
        if err:
            return err

        try:
            horizon_days = _parse_int(request.query_params, "horizon_days", 30)
            near_expiry_days = _parse_int(request.query_params, "near_expiry_days", 90)
            usage_window_days = _parse_int(
                request.query_params, "usage_window_days", 30
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_query"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        as_of = date.today()
        product_ids = get_facility_product_ids(
            facility, usage_window_days=usage_window_days, as_of=as_of
        )
        products = Product.objects.filter(id__in=product_ids, active=True).order_by(
            "name"
        )

        items = [
            get_product_summary(
                facility,
                product,
                horizon_days=horizon_days,
                near_expiry_days=near_expiry_days,
                usage_window_days=usage_window_days,
                as_of=as_of,
            )
            for product in products
        ]

        payload = {
            "facility_id": facility.id,
            "facility_name": facility.name,
            "as_of": as_of,
            "horizon_days": horizon_days,
            "near_expiry_days": near_expiry_days,
            "usage_window_days": usage_window_days,
            "items": items,
        }
        return Response(InventorySummarySerializer(payload).data)

@extend_schema(tags=["Inventory"])
class InventoryShortagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility, err = _resolve_facility(request)
        if err:
            return err

        try:
            horizon_days = _parse_int(request.query_params, "horizon_days", 30)
            near_expiry_days = _parse_int(request.query_params, "near_expiry_days", 90)
            usage_window_days = _parse_int(
                request.query_params, "usage_window_days", 30
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_query"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        as_of = date.today()
        product_ids = get_facility_product_ids(
            facility, usage_window_days=usage_window_days, as_of=as_of
        )
        products = Product.objects.filter(id__in=product_ids, active=True)

        items = []
        for product in products:
            row = get_product_summary(
                facility,
                product,
                horizon_days=horizon_days,
                near_expiry_days=near_expiry_days,
                usage_window_days=usage_window_days,
                as_of=as_of,
            )
            if row["projected_gap"] is not None and row["projected_gap"] > 0:
                items.append(row)

        items.sort(key=lambda r: (-r["projected_gap"], r["product_name"]))

        payload = {
            "facility_id": facility.id,
            "facility_name": facility.name,
            "as_of": as_of,
            "horizon_days": horizon_days,
            "near_expiry_days": near_expiry_days,
            "usage_window_days": usage_window_days,
            "items": items,
        }
        return Response(InventorySummarySerializer(payload).data)

@extend_schema(tags=["Inventory"])
class InventoryExpiringView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility, err = _resolve_facility(request)
        if err:
            return err

        try:
            days = _parse_int(request.query_params, "days", 90)
        except ValueError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_query"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        as_of = date.today()
        batches = get_near_expiry_batches(facility, days=days, as_of=as_of)

        rows = [
            {
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "product_id": b.product_id,
                "product_name": b.product.name,
                "category": b.product.category,
                "quantity_available": b.quantity_available,
                "expiry_date": b.expiry_date,
                "days_until_expiry": (b.expiry_date - as_of).days,
                "storage_status": b.storage_status,
            }
            for b in batches
        ]

        payload = {
            "facility_id": facility.id,
            "facility_name": facility.name,
            "as_of": as_of,
            "near_expiry_days": days,
            "batches": rows,
        }
        return Response(ExpiringBatchesSerializer(payload).data)


# ----------------------------- Transfers -----------------------------


def _transfer_error_response(exc):
    return Response(
        {"detail": str(exc), "code": "transfer_error"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _transfer_state_conflict(exc):
    return Response(
        {"detail": str(exc), "code": "invalid_state"},
        status=status.HTTP_409_CONFLICT,
    )

@extend_schema(tags=["Transfers"])
class TransferRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    filterset_fields = ("status", "priority", "source_facility", "destination_facility", "product")
    search_fields = ("source_facility__name", "destination_facility__name", "product__name")
    ordering_fields = ("created_at", "updated_at", "priority")
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return TransferRequestCreateSerializer
        return TransferRequestSerializer

    def get_queryset(self):
        user = self.request.user
        qs = TransferRequest.objects.select_related(
            "source_facility",
            "destination_facility",
            "product",
            "source_batch",
            "requested_by",
            "approved_by",
        )
        if user.role in (User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR):
            return qs
        if user.facility_id:
            return qs.filter(
                models.Q(source_facility_id=user.facility_id)
                | models.Q(destination_facility_id=user.facility_id)
            )
        return qs.none()

    # -------------------- Create --------------------

    def create(self, request, *args, **kwargs):
        user = request.user
        if user.role not in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
            User.Role.FACILITY_MANAGER,
            User.Role.PHARMACIST,
            User.Role.INVENTORY_STAFF,
        ):
            return Response(
                {
                    "detail": "Your role cannot request transfers.",
                    "code": "forbidden",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        ser = TransferRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        source = ser.validated_data["source_facility"]
        destination = ser.validated_data["destination_facility"]

        is_central = user.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )
        if not is_central:
            if not user.facility_id or user.facility_id not in (
                source.id,
                destination.id,
            ):
                return Response(
                    {
                        "detail": "You must belong to the source or destination facility.",
                        "code": "forbidden",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            transfer = create_transfer_request(
                source_facility=source,
                destination_facility=destination,
                product=ser.validated_data["product"],
                source_batch=ser.validated_data["source_batch"],
                quantity_requested=ser.validated_data["quantity_requested"],
                priority=ser.validated_data["priority"],
                requested_by=user,
                expected_dispatch_at=ser.validated_data.get("expected_dispatch_at"),
                expected_arrival_at=ser.validated_data.get("expected_arrival_at"),
                notes=ser.validated_data.get("notes", ""),
            )
        except TransferError as exc:
            return _transfer_error_response(exc)

        log_audit(
            user,
            "TRANSFER_REQUESTED",
            "TransferRequest",
            transfer.id,
            metadata={
                "source_facility_id": source.id,
                "destination_facility_id": destination.id,
                "product_id": transfer.product_id,
                "quantity_requested": transfer.quantity_requested,
            },
            ip_address=_ip(request),
        )
        return Response(
            TransferRequestSerializer(transfer).data, status=status.HTTP_201_CREATED
        )

    # -------------------- Approve --------------------

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        user = request.user
        is_central = user.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )
        if not is_central:
            if not (
                user.role == User.Role.FACILITY_MANAGER
                and user.facility_id == transfer.source_facility_id
            ):
                return Response(
                    {
                        "detail": "Only central users or the source facility manager can approve.",
                        "code": "forbidden",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = TransferApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        qty = ser.validated_data.get("quantity_approved", transfer.quantity_requested)

        try:
            transfer = approve_transfer(
                transfer=transfer, approved_by=user, quantity_approved=qty
            )
        except TransferError as exc:
            if "Cannot approve" in str(exc):
                return _transfer_state_conflict(exc)
            return _transfer_error_response(exc)

        log_audit(
            user,
            "TRANSFER_APPROVED",
            "TransferRequest",
            transfer.id,
            metadata={"quantity_approved": qty},
            ip_address=_ip(request),
        )
        return Response(TransferRequestSerializer(transfer).data)

    # -------------------- Reject --------------------

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        transfer = self.get_object()
        user = request.user
        is_central = user.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )
        if not is_central:
            if not (
                user.role == User.Role.FACILITY_MANAGER
                and user.facility_id
                in (transfer.source_facility_id, transfer.destination_facility_id)
            ):
                return Response(
                    {"detail": "Not authorized.", "code": "forbidden"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = TransferRejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            transfer = reject_transfer(
                transfer=transfer,
                reviewed_by=user,
                rejection_reason=ser.validated_data["rejection_reason"],
            )
        except TransferError as exc:
            if "Cannot reject" in str(exc):
                return _transfer_state_conflict(exc)
            return _transfer_error_response(exc)

        log_audit(
            user,
            "TRANSFER_REJECTED",
            "TransferRequest",
            transfer.id,
            metadata={"reason": transfer.rejection_reason},
            ip_address=_ip(request),
        )
        return Response(TransferRequestSerializer(transfer).data)

    # -------------------- Dispatch --------------------

    @action(detail=True, methods=["post"], url_path="dispatch",)
    def dispatched(self, request, pk=None):
        transfer = self.get_object()
        user = request.user
        is_central = user.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )
        if not is_central:
            if not (
                user.facility_id == transfer.source_facility_id
                and user.role
                in (
                    User.Role.FACILITY_MANAGER,
                    User.Role.PHARMACIST,
                    User.Role.INVENTORY_STAFF,
                )
            ):
                return Response(
                    {
                        "detail": "Only source facility staff can dispatch.",
                        "code": "forbidden",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = TransferDispatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            transfer = dispatch_transfer(
                transfer=transfer,
                performed_by=user,
                notes=ser.validated_data.get("notes", ""),
            )
        except TransferError as exc:
            if "Cannot dispatch" in str(exc):
                return _transfer_state_conflict(exc)
            return _transfer_error_response(exc)

        log_audit(
            user,
            "TRANSFER_DISPATCHED",
            "TransferRequest",
            transfer.id,
            metadata={"quantity": transfer.quantity_approved},
            ip_address=_ip(request),
        )
        return Response(TransferRequestSerializer(transfer).data)

    # -------------------- Receive --------------------

    @action(detail=True, methods=["post"], url_path="confirm-receipt")
    def confirm_receipt(self, request, pk=None):
        transfer = self.get_object()
        user = request.user
        is_central = user.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )
        if not is_central:
            if not (
                user.facility_id == transfer.destination_facility_id
                and user.role
                in (
                    User.Role.FACILITY_MANAGER,
                    User.Role.PHARMACIST,
                    User.Role.INVENTORY_STAFF,
                )
            ):
                return Response(
                    {
                        "detail": "Only destination facility staff can confirm receipt.",
                        "code": "forbidden",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = TransferReceiptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            transfer, dest_batch = receive_transfer(
                transfer=transfer,
                performed_by=user,
                quantity_received=ser.validated_data["quantity_received"],
                condition=ser.validated_data["condition"],
                notes=ser.validated_data.get("notes", ""),
            )
        except TransferError as exc:
            if "Cannot receive" in str(exc):
                return _transfer_state_conflict(exc)
            return _transfer_error_response(exc)

        log_audit(
            user,
            "TRANSFER_RECEIVED",
            "TransferRequest",
            transfer.id,
            metadata={
                "quantity_received": transfer.quantity_received,
                "condition": transfer.condition_on_receipt,
                "destination_batch_id": dest_batch.id,
            },
            ip_address=_ip(request),
        )

        if transfer.quantity_received < transfer.quantity_approved:
            log_audit(
                user,
                "TRANSFER_DISCREPANCY",
                "TransferRequest",
                transfer.id,
                metadata={
                    "approved": transfer.quantity_approved,
                    "received": transfer.quantity_received,
                    "delta": transfer.quantity_approved
                    - transfer.quantity_received,
                },
                ip_address=_ip(request),
            )

        return Response(TransferRequestSerializer(transfer).data)

    # -------------------- Cancel --------------------

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        user = request.user
        is_central = user.role in (
            User.Role.SYSTEM_ADMIN,
            User.Role.CENTRAL_COORDINATOR,
        )
        if not is_central:
            if not (
                user.facility_id
                in (transfer.source_facility_id, transfer.destination_facility_id)
            ):
                return Response(
                    {"detail": "Not authorized.", "code": "forbidden"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = TransferCancelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            transfer = cancel_transfer(
                transfer=transfer,
                performed_by=user,
                reason=ser.validated_data.get("reason", ""),
            )
        except TransferError as exc:
            if "Cannot cancel" in str(exc):
                return _transfer_state_conflict(exc)
            return _transfer_error_response(exc)

        log_audit(
            user,
            "TRANSFER_CANCELLED",
            "TransferRequest",
            transfer.id,
            metadata={"reason": ser.validated_data.get("reason", "")},
            ip_address=_ip(request),
        )
        return Response(TransferRequestSerializer(transfer).data)