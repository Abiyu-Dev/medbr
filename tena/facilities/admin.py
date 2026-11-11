from django.contrib import admin
from .models import Facility


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "facility_type",
        "region",
        "status",
        "is_active",
        "submitted_by",
        "reviewed_by",
    )
    list_filter = ("facility_type", "status", "region", "has_cold_chain", "is_active")
    search_fields = ("name", "registration_number", "region", "town")
    readonly_fields = ("submitted_by", "reviewed_by", "reviewed_at", "created_at", "updated_at")