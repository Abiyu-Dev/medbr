import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Patient(models.Model):
    """Vaccination-purpose patient record. No diagnoses or general medical notes."""

    class Sex(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        OTHER = "OTHER", "Other"
        UNKNOWN = "UNKNOWN", "Unknown"

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="patients"
    )
    patient_number = models.CharField(max_length=32)
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField()
    sex = models.CharField(
        max_length=16, choices=Sex.choices, default=Sex.UNKNOWN
    )
    guardian_name = models.CharField(max_length=255, blank=True)
    guardian_phone = models.CharField(max_length=32, blank=True)
    patient_phone = models.CharField(max_length=32, blank=True)
    address_area = models.CharField(max_length=255, blank=True)
    consent_given = models.BooleanField(default=False)
    consent_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patients_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("facility", "patient_number")]
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["facility", "active"]),
            models.Index(fields=["patient_number"]),
        ]

    def __str__(self):
        return f"{self.patient_number} - {self.full_name}"

    def clean(self):
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            raise ValidationError({"date_of_birth": "Cannot be in the future."})


class VaccineSchedule(models.Model):
    """
    Versioned schedule rules from an approved source.
    A new version supersedes the previous one; historical records keep their FK.
    """

    vaccine_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="schedules",
    )
    dose_number = models.PositiveIntegerField()
    recommended_age_days = models.PositiveIntegerField(null=True, blank=True)
    recommended_age_label = models.CharField(max_length=64, blank=True)
    minimum_interval_days = models.PositiveIntegerField(null=True, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    source_name = models.CharField(max_length=255)
    source_version = models.CharField(max_length=64, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules_approved",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["vaccine_product", "dose_number"]
        indexes = [
            models.Index(fields=["vaccine_product", "dose_number", "active"]),
        ]

    def __str__(self):
        return (
            f"{self.vaccine_product.name} dose {self.dose_number} "
            f"(v{self.id}, active={self.active})"
        )

    def clean(self):
        if self.vaccine_product_id:
            if self.vaccine_product.category != "VACCINE":
                raise ValidationError(
                    {"vaccine_product": "Product must have category VACCINE."}
                )
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError(
                {"effective_to": "Must be on or after effective_from."}
            )
        if self.dose_number < 1:
            raise ValidationError({"dose_number": "Must be >= 1."})
        if self.recommended_age_days is None and self.minimum_interval_days is None:
            raise ValidationError(
                "At least one of recommended_age_days or minimum_interval_days "
                "must be set so due dates can be computed."
            )


class VaccinationRecord(models.Model):
    """
    An actual administered dose. This is the ONLY path that creates a
    VACCINATION_ADMINISTRATION stock movement.
    """

    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="vaccination_records"
    )
    vaccine_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="vaccination_records",
    )
    schedule = models.ForeignKey(
        VaccineSchedule,
        on_delete=models.PROTECT,
        related_name="records",
        null=True,
        blank=True,
    )
    dose_number = models.PositiveIntegerField()
    administered_at = models.DateTimeField()
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="vaccination_records",
    )
    batch = models.ForeignKey(
        "inventory.StockBatch",
        on_delete=models.PROTECT,
        related_name="vaccination_records",
    )
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vaccinations_recorded",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("patient", "vaccine_product", "dose_number")]
        ordering = ["-administered_at"]
        indexes = [
            models.Index(fields=["patient", "vaccine_product"]),
            models.Index(fields=["facility", "administered_at"]),
        ]

    def __str__(self):
        return (
            f"{self.patient.patient_number} - "
            f"{self.vaccine_product.name} dose {self.dose_number}"
        )


class VaccineFollowUp(models.Model):
    """
    Scheduled follow-up for a patient's next due dose.
    Created automatically on record creation, or manually by a health worker.
    """

    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        DUE = "DUE", "Due"
        OVERDUE = "OVERDUE", "Overdue"
        COMPLETED = "COMPLETED", "Completed"
        CONTACT_ATTEMPTED = "CONTACT_ATTEMPTED", "Contact Attempted"
        REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review Required"
        CANCELLED = "CANCELLED", "Cancelled"

    class ContactOutcome(models.TextChoices):
        REACHED = "REACHED", "Reached"
        NO_ANSWER = "NO_ANSWER", "No Answer"
        RESCHEDULED = "RESCHEDULED", "Rescheduled"
        REFERRED_FOR_REVIEW = "REFERRED_FOR_REVIEW", "Referred for Review"

    OPEN_STATUSES = [
        Status.UPCOMING,
        Status.DUE,
        Status.OVERDUE,
        Status.CONTACT_ATTEMPTED,
        Status.REVIEW_REQUIRED,
    ]
    TERMINAL_STATUSES = [Status.COMPLETED, Status.CANCELLED]

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="follow_ups"
    )
    vaccine_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="follow_ups",
    )
    dose_number = models.PositiveIntegerField()
    due_date = models.DateField()
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.UPCOMING
    )
    assigned_to = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="follow_ups_assigned",
    )
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    contact_outcome = models.CharField(
        max_length=32,
        choices=ContactOutcome.choices,
        blank=True,
    )
    next_action_date = models.DateField(null=True, blank=True)
    review_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date"]
        indexes = [
            models.Index(fields=["patient", "vaccine_product"]),
            models.Index(fields=["status", "due_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "vaccine_product", "dose_number"],
                condition=models.Q(
                    status__in=[
                        "UPCOMING",
                        "DUE",
                        "OVERDUE",
                        "CONTACT_ATTEMPTED",
                        "REVIEW_REQUIRED",
                    ]
                ),
                name="unique_open_follow_up_per_dose",
            )
        ]

    def __str__(self):
        return (
            f"Follow-up {self.patient.patient_number} - "
            f"{self.vaccine_product.name} dose {self.dose_number} ({self.status})"
        )

    def effective_status(self, today=None):
        """
        Time-aware status for display and filtering.
        Terminal/user-set states win; otherwise infer from due_date.
        """
        today = today or timezone.localdate()
        if self.status in (
            self.Status.COMPLETED,
            self.Status.CANCELLED,
            self.Status.REVIEW_REQUIRED,
            self.Status.CONTACT_ATTEMPTED,
        ):
            return self.status
        if self.due_date < today:
            return self.Status.OVERDUE
        if self.due_date == today:
            return self.Status.DUE
        return self.Status.UPCOMING