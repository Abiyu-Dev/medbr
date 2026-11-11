from datetime import date

from rest_framework import serializers

from accounts.models import User

from .models import *




class TransferRequestSerializer(serializers.ModelSerializer):
    source_facility_name = serializers.CharField(
        source="source_facility.name", read_only=True
    )
    destination_facility_name = serializers.CharField(
        source="destination_facility.name", read_only=True
    )
    product_name = serializers.CharField(source="product.name", read_only=True)
    source_batch_number = serializers.CharField(
        source="source_batch.batch_number", read_only=True
    )
    source_batch_expiry = serializers.DateField(
        source="source_batch.expiry_date", read_only=True
    )
    requested_by_username = serializers.CharField(
        source="requested_by.username", read_only=True, default=None
    )
    approved_by_username = serializers.CharField(
        source="approved_by.username", read_only=True, default=None
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(
        source="get_priority_display", read_only=True
    )

    class Meta:
        model = TransferRequest
        fields = "__all__"
        read_only_fields = (
            "id",
            "status",
            "quantity_approved",
            "quantity_received",
            "requested_by",
            "requested_by_username",
            "approved_by",
            "approved_by_username",
            "approved_at",
            "rejection_reason",
            "received_by",
            "received_at",
            "condition_on_receipt",
            "created_at",
            "updated_at",
        )


class TransferRequestCreateSerializer(serializers.Serializer):
    source_facility = serializers.PrimaryKeyRelatedField(
        queryset=__import__("facilities.models", fromlist=["Facility"]).Facility.objects.filter(
            status="APPROVED", is_active=True
        )
    )
    destination_facility = serializers.PrimaryKeyRelatedField(
        queryset=__import__("facilities.models", fromlist=["Facility"]).Facility.objects.filter(
            status="APPROVED", is_active=True
        )
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(active=True)
    )
    source_batch = serializers.PrimaryKeyRelatedField(queryset=StockBatch.objects.all())
    quantity_requested = serializers.IntegerField(min_value=1)
    priority = serializers.ChoiceField(
        choices=[p for p in TransferRequest.Priority.values], default="MEDIUM"
    )
    expected_dispatch_at = serializers.DateTimeField(required=False, allow_null=True)
    expected_arrival_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TransferApproveSerializer(serializers.Serializer):
    quantity_approved = serializers.IntegerField(min_value=1, required=False)


class TransferRejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=True, allow_blank=False)


class TransferDispatchSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TransferReceiptSerializer(serializers.Serializer):
    quantity_received = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(
        choices=["OK", "DAMAGED", "TEMPERATURE_EXCURSION"], default="OK"
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TransferCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ----------------------------- Products -----------------------------




class ProductSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


# ----------------------------- Batches -----------------------------


class StockBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_category = serializers.CharField(source="product.category", read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    storage_status_display = serializers.CharField(
        source="get_storage_status_display", read_only=True
    )
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockBatch
        fields = (
            "id",
            "facility",
            "facility_name",
            "product",
            "product_name",
            "product_category",
            "batch_number",
            "expiry_date",
            "quantity_received",
            "quantity_available",
            "quantity_reserved",
            "storage_status",
            "storage_status_display",
            "received_at",
            "source_reference",
            "is_expired",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "facility",
            "facility_name",
            "product",
            "product_name",
            "product_category",
            "batch_number",
            "expiry_date",
            "quantity_received",
            "quantity_available",
            "quantity_reserved",
            "storage_status_display",
            "received_at",
            "is_expired",
            "created_by",
            "created_at",
            "updated_at",
        )


class StockBatchUpdateSerializer(serializers.ModelSerializer):
    """Only status and free-text reference — never quantities."""

    class Meta:
        model = StockBatch
        fields = ("storage_status", "source_reference")


# ----------------------------- Movements -----------------------------


class StockMovementSerializer(serializers.ModelSerializer):
    movement_type_display = serializers.CharField(
        source="get_movement_type_display", read_only=True
    )
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    product_name = serializers.CharField(source="batch.product.name", read_only=True)
    product_category = serializers.CharField(
        source="batch.product.category", read_only=True
    )
    facility_id = serializers.IntegerField(source="batch.facility_id", read_only=True)
    facility_name = serializers.CharField(
        source="batch.facility.name", read_only=True
    )
    performed_by_username = serializers.CharField(
        source="performed_by.username", read_only=True, default=None
    )

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "batch",
            "batch_number",
            "product_name",
            "product_category",
            "facility_id",
            "facility_name",
            "movement_type",
            "movement_type_display",
            "direction",
            "quantity",
            "reference_type",
            "reference_id",
            "reason",
            "performed_by",
            "performed_by_username",
            "occurred_at",
            "created_at",
            "idempotency_key",
        )
        read_only_fields = fields


# ----------------------------- Action request bodies -----------------------------
#
# The batch field's queryset is narrowed to the caller's facility scope at
# init time, so cross-facility batch IDs look identical to non-existent IDs
# (400 "invalid pk" in both cases → no information leak).


class _BatchScopedSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request:
            return
        user = request.user
        if user.role == User.Role.SYSTEM_ADMIN:
            qs = StockBatch.objects.all()
        elif user.facility_id:
            qs = StockBatch.objects.filter(facility_id=user.facility_id)
        else:
            qs = StockBatch.objects.none()
        self.fields["batch"].queryset = qs


class StockReceiptSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(active=True)
    )
    batch_number = serializers.CharField(max_length=64)
    expiry_date = serializers.DateField()
    quantity = serializers.IntegerField(min_value=1)
    source_reference = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )

    def validate_expiry_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("Expiry date cannot be in the past.")
        return value


class StockConsumptionSerializer(_BatchScopedSerializer):
    batch = serializers.PrimaryKeyRelatedField(queryset=StockBatch.objects.none())
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    reference_type = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    reference_id = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )


class StockWastageSerializer(_BatchScopedSerializer):
    batch = serializers.PrimaryKeyRelatedField(queryset=StockBatch.objects.none())
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=True, allow_blank=False)
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )


class StockAdjustmentSerializer(_BatchScopedSerializer):
    batch = serializers.PrimaryKeyRelatedField(queryset=StockBatch.objects.none())
    quantity = serializers.IntegerField(min_value=1)
    direction = serializers.ChoiceField(choices=["IN", "OUT"])
    reason = serializers.CharField(required=True, allow_blank=False)
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )


# ----------------------------- Equipment -----------------------------


class EquipmentSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    condition_display = serializers.CharField(
        source="get_condition_display", read_only=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )

    class Meta:
        model = Equipment
        fields = (
            "id",
            "facility",
            "facility_name",
            "name",
            "category",
            "asset_identifier",
            "quantity",
            "condition",
            "condition_display",
            "notes",
            "last_checked_at",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "facility_name",
            "condition_display",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )


class EquipmentUpdateSerializer(serializers.ModelSerializer):
    """Facility cannot be changed after creation."""

    class Meta:
        model = Equipment
        fields = (
            "name",
            "category",
            "asset_identifier",
            "quantity",
            "condition",
            "notes",
            "last_checked_at",
        )


# ----------------------------- Inventory rollups -----------------------------


class InventoryItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    category = serializers.CharField()
    unit_of_measure = serializers.CharField()
    usable_stock = serializers.IntegerField()
    reserved_stock = serializers.IntegerField()
    incoming_stock = serializers.IntegerField()
    projected_demand = serializers.IntegerField(allow_null=True)
    projected_gap = serializers.IntegerField(allow_null=True)
    days_of_stock = serializers.FloatField(allow_null=True)
    estimated_daily_usage = serializers.FloatField(allow_null=True)
    follow_up_demand = serializers.IntegerField()
    near_expiry_quantity = serializers.IntegerField()
    batch_count = serializers.IntegerField()


class InventorySummarySerializer(serializers.Serializer):
    facility_id = serializers.IntegerField()
    facility_name = serializers.CharField()
    as_of = serializers.DateField()
    horizon_days = serializers.IntegerField()
    near_expiry_days = serializers.IntegerField()
    usage_window_days = serializers.IntegerField()
    items = InventoryItemSerializer(many=True)


class ExpiringBatchSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    batch_number = serializers.CharField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    category = serializers.CharField()
    quantity_available = serializers.IntegerField()
    expiry_date = serializers.DateField()
    days_until_expiry = serializers.IntegerField()
    storage_status = serializers.CharField()


class ExpiringBatchesSerializer(serializers.Serializer):
    facility_id = serializers.IntegerField()
    facility_name = serializers.CharField()
    as_of = serializers.DateField()
    near_expiry_days = serializers.IntegerField()
    batches = ExpiringBatchSerializer(many=True)