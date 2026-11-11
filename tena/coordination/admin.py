from django.contrib import admin

from .models import DeliveryCoordination, SupplyGapReport


@admin.register(DeliveryCoordination)
class DeliveryCoordinationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "transfer_request",
        "delivery_status",
        "transport_payer",
        "coordinator",
        "created_at",
    )
    list_filter = ("delivery_status", "transport_payer")
    search_fields = ("contact_person_name", "contact_phone", "notes")


@admin.register(SupplyGapReport)
class SupplyGapReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "facility",
        "product",
        "priority",
        "uncovered_quantity",
        "status",
        "assigned_to",
    )
    list_filter = ("status", "priority")
    search_fields = ("facility__name", "product__name", "reason_summary")