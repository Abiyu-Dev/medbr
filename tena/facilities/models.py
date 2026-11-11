from django.core.exceptions import ValidationError
from django.db import models


class Facility(models.Model):
    class FacilityType(models.TextChoices):
        CLINIC = "CLINIC", "Clinic"
        HOSPITAL = "HOSPITAL", "Hospital"
        HEALTH_CENTER = "HEALTH_CENTER", "Health Center"
        PHARMACY = "PHARMACY", "Pharmacy"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"

    name = models.CharField(max_length=255)
    facility_type = models.CharField(max_length=32, choices=FacilityType.choices)
    registration_number = models.CharField(
        max_length=64, blank=True, null=True, unique=True
    )

    region = models.CharField(max_length=64)
    zone = models.CharField(max_length=64, blank=True)
    woreda = models.CharField(max_length=64, blank=True)
    kebele = models.CharField(max_length=64, blank=True)
    town = models.CharField(max_length=64, blank=True)

    address = models.TextField(blank=True)
    landmark = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    contact_phone = models.CharField(max_length=32, blank=True)
    contact_email = models.EmailField(blank=True)

    storage_capacity_notes = models.TextField(blank=True)
    has_cold_chain = models.BooleanField(default=False)
    cold_chain_notes = models.TextField(blank=True)
    provides_vaccination_services = models.BooleanField(default=False)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    is_active = models.BooleanField(default=True)

    submitted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_facilities",
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_facilities",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_facility_type_display()})"

    def clean(self):
        if self.latitude is not None and not (-90 <= float(self.latitude) <= 90):
            raise ValidationError({"latitude": "Latitude must be between -90 and 90."})
        if self.longitude is not None and not (-180 <= float(self.longitude) <= 180):
            raise ValidationError({"longitude": "Longitude must be between -180 and 180."})