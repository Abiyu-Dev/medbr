from django.contrib import admin

from .models import AIRecommendation


@admin.register(AIRecommendation)
class AIRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "analysis_type",
        "status",
        "scope_facility",
        "model_name",
        "requested_by",
        "created_at",
    )
    list_filter = ("analysis_type", "status")
    search_fields = ("summary", "error", "review_note")
    readonly_fields = (
        "input_snapshot",
        "raw_output",
        "validated_output",
        "validation_errors",
        "created_at",
        "updated_at",
        "model_name",
        "requested_by",
    )