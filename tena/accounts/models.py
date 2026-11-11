from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        SYSTEM_ADMIN = "SYSTEM_ADMIN", "System Admin"
        CENTRAL_COORDINATOR = "CENTRAL_COORDINATOR", "Central Coordinator"
        FACILITY_MANAGER = "FACILITY_MANAGER", "Facility Manager"
        PHARMACIST = "PHARMACIST", "Pharmacist"
        INVENTORY_STAFF = "INVENTORY_STAFF", "Inventory Staff"
        PHARMACY_STAFF = "PHARMACY_STAFF", "Pharmacy Staff"
        HEALTH_WORKER = "HEALTH_WORKER", "Health Worker"

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=32, choices=Role.choices, default=Role.HEALTH_WORKER
    )
    # FK resolved lazily so we can declare User before Facility is migrated
    facility = models.ForeignKey(
        "facilities.Facility",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    phone = models.CharField(max_length=32, blank=True)

    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return f"{self.username} ({self.role})"


class AuditLog(models.Model):
    """Append-only operational audit. Never updated or deleted in the MVP."""

    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}#{self.entity_id}"