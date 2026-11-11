from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Product(models.Model):
    """One catalogue for medicines AND vaccines; batch logic is shared."""

    class Category(models.TextChoices):
        MEDICINE = "MEDICINE", "Medicine"
        VACCINE = "VACCINE", "Vaccine"

    name = models.CharField(max_length=255)
    category = models.CharField(max_length=16, choices=Category.choices)
    generic_name = models.CharField(max_length=255, blank=True)
    strength = models.CharField(max_length=64, blank=True)
    dosage_form = models.CharField(max_length=64, blank=True)
    unit_of_measure = models.CharField(max_length=32, default="dose")
    description = models.TextField(blank=True)
    requires_cold_chain = models.BooleanField(default=False)
    storage_min_temperature = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    storage_max_temperature = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["category", "active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def clean(self):
        if self.category not in (self.Category.MEDICINE, self.Category.VACCINE):
            raise ValidationError({"category": "Must be MEDICINE or VACCINE."})
        if (
            self.storage_min_temperature is not None
            and self.storage_max_temperature is not None
            and self.storage_min_temperature > self.storage_max_temperature
        ):
            raise ValidationError("storage_min_temperature must be <= storage_max_temperature.")


class StockBatch(models.Model):
    """
    A batch of a product held at a specific facility.
    quantity_available is maintained by the stock service within atomic transactions.
    Never mutate it directly outside inventory.services.
    """

    class StorageStatus(models.TextChoices):
        OK = "OK", "OK"
        QUARANTINED = "QUARANTINED", "Quarantined"
        TEMPERATURE_EXCURSION = "TEMPERATURE_EXCURSION", "Temperature Excursion"
        DAMAGED = "DAMAGED", "Damaged"
        EXPIRED = "EXPIRED", "Expired"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="batches"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=64)
    expiry_date = models.DateField()
    quantity_received = models.PositiveIntegerField(default=0)
    quantity_available = models.PositiveIntegerField(default=0)
    quantity_reserved = models.PositiveIntegerField(default=0)
    storage_status = models.CharField(
        max_length=32, choices=StorageStatus.choices, default=StorageStatus.OK
    )
    received_at = models.DateTimeField(auto_now_add=True)
    source_reference = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("facility", "product", "batch_number")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["facility", "product"]),
            models.Index(fields=["expiry_date"]),
            models.Index(fields=["storage_status"]),
        ]

    def __str__(self):
        return f"{self.batch_number} / {self.product.name} @ {self.facility.name}"

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()

    def is_usable(self):
        return self.storage_status == self.StorageStatus.OK and not self.is_expired


class StockMovement(models.Model):
    """
    Append-only ledger. The single source of truth for stock changes.
    Rows are never updated or deleted; corrections happen via new ADJUSTMENT entries.
    """

    class MovementType(models.TextChoices):
        RECEIPT = "RECEIPT", "Receipt"
        CONSUMPTION = "CONSUMPTION", "Consumption"
        VACCINATION_ADMINISTRATION = "VACCINATION_ADMINISTRATION", "Vaccination Administration"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"
        WASTAGE = "WASTAGE", "Wastage"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        RETURN = "RETURN", "Return"

    class Direction(models.TextChoices):
        IN = "IN", "In"
        OUT = "OUT", "Out"

    # Non-adjustment types have their direction fully determined by type.
    FIXED_DIRECTION = {
        MovementType.RECEIPT: Direction.IN,
        MovementType.CONSUMPTION: Direction.OUT,
        MovementType.VACCINATION_ADMINISTRATION: Direction.OUT,
        MovementType.TRANSFER_OUT: Direction.OUT,
        MovementType.TRANSFER_IN: Direction.IN,
        MovementType.WASTAGE: Direction.OUT,
        MovementType.RETURN: Direction.IN,
    }

    batch = models.ForeignKey(
        StockBatch, on_delete=models.PROTECT, related_name="movements"
    )
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    quantity = models.PositiveIntegerField()
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    reason = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(
        max_length=128, unique=True, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["batch", "movement_type"]),
            models.Index(fields=["occurred_at"]),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.direction} {self.quantity} #{self.batch_id}"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Must be positive."})
        fixed = self.FIXED_DIRECTION.get(self.movement_type)
        if fixed and self.direction != fixed:
            raise ValidationError(
                {"direction": f"{self.movement_type} must be {fixed}."}
            )



class Equipment(models.Model):
    """Non-stock assets (fridges, cold boxes, scales, etc.) at a facility."""

    class Condition(models.TextChoices):
        OPERATIONAL = "OPERATIONAL", "Operational"
        NEEDS_MAINTENANCE = "NEEDS_MAINTENANCE", "Needs Maintenance"
        OUT_OF_SERVICE = "OUT_OF_SERVICE", "Out of Service"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="equipment"
    )
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=64, blank=True)
    asset_identifier = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(
        max_length=32, choices=Condition.choices, default=Condition.OPERATIONAL
    )
    notes = models.TextField(blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["facility", "condition"])]

    def __str__(self):
        return f"{self.name} @ {self.facility.name}"



class TransferRequest(models.Model):
    """
    A batch-level stock transfer between two facilities.
    One product / one batch per request (MVP).
    Dispatch and receipt are the ONLY operations that write stock ledger movements.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        REQUESTED = "REQUESTED", "Requested"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        DISPATCHED = "DISPATCHED", "Dispatched"
        IN_TRANSIT = "IN_TRANSIT", "In Transit"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"

    class Priority(models.TextChoices):
        CRITICAL = "CRITICAL", "Critical"
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    source_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )
    destination_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="transfers"
    )
    source_batch = models.ForeignKey(
        StockBatch, on_delete=models.PROTECT, related_name="transfers"
    )

    quantity_requested = models.PositiveIntegerField()
    quantity_approved = models.PositiveIntegerField(default=0)
    quantity_received = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.REQUESTED
    )
    priority = models.CharField(
        max_length=16, choices=Priority.choices, default=Priority.MEDIUM
    )

    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="transfers_requested",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    received_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_received",
    )
    received_at = models.DateTimeField(null=True, blank=True)
    condition_on_receipt = models.CharField(max_length=32, blank=True)

    expected_dispatch_at = models.DateTimeField(null=True, blank=True)
    expected_arrival_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "destination_facility"]),
            models.Index(fields=["status", "source_facility"]),
        ]

    def __str__(self):
        return (
            f"Transfer #{self.id}: {self.source_facility_id} -> "
            f"{self.destination_facility_id} ({self.status})"
        )

    TRANSITIONS = {
        Status.DRAFT: {Status.REQUESTED, Status.CANCELLED},
        Status.REQUESTED: {
            Status.UNDER_REVIEW,
            Status.APPROVED,
            Status.REJECTED,
            Status.CANCELLED,
        },
        Status.UNDER_REVIEW: {Status.APPROVED, Status.REJECTED, Status.CANCELLED},
        Status.APPROVED: {Status.DISPATCHED, Status.CANCELLED},
        Status.DISPATCHED: {Status.IN_TRANSIT, Status.RECEIVED, Status.FAILED},
        Status.IN_TRANSIT: {Status.RECEIVED, Status.FAILED},
        Status.RECEIVED: set(),
        Status.REJECTED: set(),
        Status.CANCELLED: set(),
        Status.FAILED: set(),
    }

    def can_transition_to(self, target):
        return target in self.TRANSITIONS.get(self.status, set())