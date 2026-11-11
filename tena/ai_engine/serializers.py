from rest_framework import serializers

from .models import AIRecommendation


class AIRecommendationSerializer(serializers.ModelSerializer):
    analysis_type_display = serializers.CharField(
        source="get_analysis_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    scope_facility_name = serializers.CharField(
        source="scope_facility.name", read_only=True, default=None
    )
    requested_by_username = serializers.CharField(
        source="requested_by.username", read_only=True, default=None
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=None
    )

    class Meta:
        model = AIRecommendation
        fields = (
            "id",
            "analysis_type",
            "analysis_type_display",
            "status",
            "status_display",
            "scope_facility",
            "scope_facility_name",
            "requested_by",
            "requested_by_username",
            "model_name",
            "summary",
            "validated_output",
            "validation_errors",
            "error",
            "reviewed_by",
            "reviewed_by_username",
            "reviewed_at",
            "review_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AIRecommendationDetailSerializer(AIRecommendationSerializer):
    supply_requests_created = serializers.SerializerMethodField()
    proposals_created = serializers.SerializerMethodField()

    def get_supply_requests_created(self, obj):
        return getattr(obj, "_created_supply_requests", None)

    def get_proposals_created(self, obj):
        return getattr(obj, "_materialized_proposals", None)

    class Meta(AIRecommendationSerializer.Meta):
        fields = AIRecommendationSerializer.Meta.fields + (
            "input_snapshot",
            "raw_output",
            "supply_requests_created",
            "proposals_created",
        )
        read_only_fields = fields


class AnalyzeInventoryRequestSerializer(serializers.Serializer):
    facility = serializers.IntegerField(required=False, allow_null=True)
    horizon_days = serializers.IntegerField(
        required=False, min_value=1, max_value=180, default=30
    )


class PrioritizeGapsRequestSerializer(serializers.Serializer):
    horizon_days = serializers.IntegerField(
        required=False, min_value=1, max_value=180, default=30
    )


class SummarizeVaccinationRequestSerializer(serializers.Serializer):
    facility = serializers.IntegerField(required=False, allow_null=True)
    horizon_days = serializers.IntegerField(
        required=False, min_value=7, max_value=180, default=30
    )


class PlanSourcingRequestSerializer(serializers.Serializer):
    supply_request_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=False
    )
    horizon_days = serializers.IntegerField(
        required=False, min_value=1, max_value=180, default=30
    )


class PlanGapSourcingSerializer(serializers.Serializer):
    gap_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=False
    )
    horizon_days = serializers.IntegerField(
        required=False, min_value=1, max_value=180, default=30
    )


class ReviewActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RejectActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=True, allow_blank=False)