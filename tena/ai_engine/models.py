from django.db import models
from django.utils import timezone


class AIRecommendation(models.Model):
    """
    Audit record for one Gemini call + its validated output.
    Never mutates stock. `approve` only marks it reviewed for operational follow-up.
    """

    class AnalysisType(models.TextChoices):
        INVENTORY_ANALYSIS = "INVENTORY_ANALYSIS", "Inventory Analysis"
        SUPPLY_GAP_PRIORITIZATION = (
            "SUPPLY_GAP_PRIORITIZATION",
            "Supply Gap Prioritization",
        )
        VACCINATION_DEMAND_SUMMARY = (
            "VACCINATION_DEMAND_SUMMARY",
            "Vaccination Demand Summary",
        )
        TRANSFER_SOURCING = "TRANSFER_SOURCING", "Transfer Sourcing"

    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        FAILED = "FAILED", "Failed"
        INVALID = "INVALID", "Invalid"

    class Priority(models.TextChoices):
        CRITICAL = "CRITICAL", "Critical"
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    analysis_type = models.CharField(max_length=32, choices=AnalysisType.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING_REVIEW
    )
    scope_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_recommendations",
        help_text="Null means a nationwide/central analysis.",
    )
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="ai_recommendations_requested",
    )
    model_name = models.CharField(max_length=64, blank=True)

    summary = models.TextField(blank=True)
    input_snapshot = models.JSONField(default=dict)
    raw_output = models.JSONField(default=dict, blank=True)
    validated_output = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_recommendations_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["analysis_type", "status"]),
            models.Index(fields=["scope_facility", "created_at"]),
        ]

    def __str__(self):
        return (
            f"AI {self.analysis_type} #{self.id} "
            f"({self.status}, facility={self.scope_facility_id})"
        )

    @property
    def is_reviewable(self):
        return self.status == self.Status.PENDING_REVIEW