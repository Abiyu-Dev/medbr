from django.db import models
from django.utils import timezone


class DeliveryCoordination(models.Model):
    """
    1..N record of phone-based delivery arrangements for a transfer.
    Each POST to /transfers/{id}/delivery-coordination/ creates a new entry so
    every call is auditable.
    """

    class Payer(models.TextChoices):
        CENTRAL = "CENTRAL", "Central"
        SENDER = "SENDER", "Sender"
        RECEIVER = "RECEIVER", "Receiver"
        PARTNER = "PARTNER", "Partner"
        UNDECIDED = "UNDECIDED", "Undecided"

    class PhoneStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"

    class DeliveryStatus(models.TextChoices):
        NOT_ARRANGED = "NOT_ARRANGED", "Not Arranged"
        ARRANGED_BY_PHONE = "ARRANGED_BY_PHONE", "Arranged by Phone"
        DISPATCHED = "DISPATCHED", "Dispatched"
        RECEIVED = "RECEIVED", "Received"
        FAILED = "FAILED", "Failed"
        DISCREPANCY = "DISCREPANCY", "Discrepancy"

    transfer_request = models.ForeignKey(
        "inventory.TransferRequest",
        on_delete=models.CASCADE,
        related_name="delivery_coordinations",
    )
    transport_method = models.CharField(max_length=64, blank=True)
    transport_provider = models.CharField(max_length=128, blank=True)
    contact_person_name = models.CharField(max_length=128, blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    transport_payer = models.CharField(
        max_length=16, choices=Payer.choices, default=Payer.UNDECIDED
    )
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=8, default="ETB")
    agreed_pickup_at = models.DateTimeField(null=True, blank=True)
    expected_arrival_at = models.DateTimeField(null=True, blank=True)
    phone_coordination_status = models.CharField(
        max_length=16, choices=PhoneStatus.choices, default=PhoneStatus.PENDING
    )
    coordinator = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="delivery_coordinations",
    )
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(
        max_length=32,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.NOT_ARRANGED,
    )
    receipt_confirmed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_receipts_confirmed",
    )
    receipt_confirmed_at = models.DateTimeField(null=True, blank=True)
    quantity_received = models.PositiveIntegerField(null=True, blank=True)
    condition_on_receipt = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["transfer_request", "created_at"])]

    def __str__(self):
        return f"Delivery for transfer #{self.transfer_request_id}"


class SupplyRequest(models.Model):
    """
    A facility's request to the central system for stock of a product.
    Created automatically when the facility approves an AI inventory
    analysis whose transfer recommendations target that facility.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PLANNED = "PLANNED", "Planned"
        FULFILLED = "FULFILLED", "Fulfilled"
        CANCELLED = "CANCELLED", "Cancelled"

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="supply_requests",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="supply_requests",
    )
    quantity = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    source_recommendation = models.ForeignKey(
        "ai_engine.AIRecommendation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_requests",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN
    )
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_requests_requested",
    )
    source_gap = models.ForeignKey(
        "SupplyGapReport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "facility"])]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "product"],
                condition=models.Q(status="OPEN"),
                name="unique_open_supply_request",
            )
        ]

    def __str__(self):
        return (
            f"Supply request #{self.id} {self.facility_id}/"
            f"{self.product_id} qty={self.quantity} ({self.status})"
        )


class SourcingProposal(models.Model):
    """
    One AI-proposed donor transfer for a supply request. Central review
    approves it (which creates the real TransferRequest) or rejects it.
    """

    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposed"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    request = models.ForeignKey(
        SupplyRequest,
        on_delete=models.CASCADE,
        related_name="proposals",
    )
    recommendation = models.ForeignKey(
        "ai_engine.AIRecommendation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sourcing_proposals",
    )
    source_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="sourcing_proposals_from",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="sourcing_proposals",
    )
    quantity = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    reason_amharic = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PROPOSED
    )
    transfer = models.ForeignKey(
        "inventory.TransferRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sourcing_proposals",
    )
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sourcing_proposals_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["request", "status"])]

    def __str__(self):
        return (
            f"Sourcing proposal #{self.id} req={self.request_id} "
            f"src={self.source_facility_id} qty={self.quantity} ({self.status})"
        )


class SupplyGapReport(models.Model):
    """
    One *active* gap per (facility, product). Terminal reports (RESOLVED/CLOSED)
    are immutable; a new gap that re-emerges creates a new report.
    """

    class Priority(models.TextChoices):
        CRITICAL = "CRITICAL", "Critical"
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        ASSIGNED = "ASSIGNED", "Assigned"
        ACTION_PLANNED = "ACTION_PLANNED", "Action Planned"
        ESCALATED = "ESCALATED", "Escalated"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    NON_TERMINAL_STATUSES = [
        Status.OPEN,
        Status.UNDER_REVIEW,
        Status.ASSIGNED,
        Status.ACTION_PLANNED,
        Status.ESCALATED,
    ]
    TERMINAL_STATUSES = [Status.RESOLVED, Status.CLOSED]

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="supply_gaps",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="supply_gaps",
    )
    reporting_horizon_start = models.DateField()
    reporting_horizon_end = models.DateField()
    projected_demand = models.IntegerField()
    usable_stock = models.IntegerField()
    reliable_incoming_quantity = models.IntegerField(default=0)
    uncovered_quantity = models.IntegerField()
    priority = models.CharField(max_length=16, choices=Priority.choices)
    reason_summary = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN
    )
    assigned_to = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_supply_gaps",
    )
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["priority", "-uncovered_quantity", "-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["facility", "product"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "product"],
                condition=models.Q(
                    status__in=[
                        "OPEN",
                        "UNDER_REVIEW",
                        "ASSIGNED",
                        "ACTION_PLANNED",
                        "ESCALATED",
                    ]
                ),
                name="unique_open_gap_per_facility_product",
            )
        ]

    def __str__(self):
        return (
            f"Gap {self.facility_id}/{self.product_id} "
            f"({self.priority}, qty={self.uncovered_quantity})"
        )

    def save(self, *args, **kwargs):
        if self.status in (self.Status.RESOLVED, self.Status.CLOSED):
            if self.resolved_at is None:
                self.resolved_at = timezone.now()
        else:
            self.resolved_at = None
        super().save(*args, **kwargs)