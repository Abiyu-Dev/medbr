from django.contrib import admin

from .models import *


@admin.register(TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_facility",
        "destination_facility",
        "product",
        "quantity_requested",
        "quantity_approved",
        "status",
        "priority",
    )
    list_filter = ("status", "priority", "source_facility", "destination_facility")
    search_fields = ("product__name", "notes", "rejection_reason")

@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "facility",
        "category",
        "quantity",
        "condition",
        "last_checked_at",
    )
    list_filter = ("condition", "category", "facility")
    search_fields = ("name", "asset_identifier", "facility__name")
    readonly_fields = ("created_by", "created_at", "updated_at")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "strength", "unit_of_measure", "requires_cold_chain", "active")
    list_filter = ("category", "requires_cold_chain", "active")
    search_fields = ("name", "generic_name")


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = (
        "batch_number",
        "product",
        "facility",
        "expiry_date",
        "quantity_available",
        "quantity_reserved",
        "storage_status",
    )
    list_filter = ("storage_status", "facility", "product__category")
    search_fields = ("batch_number", "product__name", "facility__name")
    readonly_fields = (
        "quantity_received",
        "quantity_available",
        "quantity_reserved",
        "received_at",
        "created_at",
        "updated_at",
        "created_by",
    )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "movement_type",
        "direction",
        "quantity",
        "batch",
        "performed_by",
    )
    list_filter = ("movement_type", "direction")
    search_fields = ("batch__batch_number", "batch__product__name", "reason")
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False