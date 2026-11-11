from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, AuditLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("MedBridge", {"fields": ("role", "facility", "phone")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("MedBridge", {"fields": ("email", "role", "facility", "phone")}),
    )
    list_display = ("username", "email", "role", "facility", "is_active")
    list_filter = ("role", "is_active", "facility")
    search_fields = ("username", "email", "phone")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "entity_type", "entity_id")
    list_filter = ("action", "entity_type")
    search_fields = ("action", "entity_type", "entity_id")
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False