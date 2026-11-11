from rest_framework import serializers

from .models import (
    DeliveryCoordination,
    SourcingProposal,
    SupplyGapReport,
    SupplyRequest,
)


class DeliveryCoordinationSerializer(serializers.ModelSerializer):
    coordinator_username = serializers.CharField(
        source="coordinator.username", read_only=True, default=None
    )
    transfer_request_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = DeliveryCoordination
        fields = "__all__"
        read_only_fields = (
            "id",
            "transfer_request",
            "coordinator",
            "coordinator_username",
            "created_at",
            "updated_at",
        )


class DeliveryCoordinationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryCoordination
        fields = (
            "transport_method",
            "transport_provider",
            "contact_person_name",
            "contact_phone",
            "transport_payer",
            "estimated_cost",
            "currency",
            "agreed_pickup_at",
            "expected_arrival_at",
            "phone_coordination_status",
            "delivery_status",
            "notes",
        )


class SupplyGapReportSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_category = serializers.CharField(
        source="product.category", read_only=True
    )
    assigned_to_username = serializers.CharField(
        source="assigned_to.username", read_only=True, default=None
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(
        source="get_priority_display", read_only=True
    )
    active_request = serializers.SerializerMethodField()

    class Meta:
        model = SupplyGapReport
        fields = "__all__"
        read_only_fields = (
            "id",
            "facility",
            "product",
            "reporting_horizon_start",
            "reporting_horizon_end",
            "projected_demand",
            "usable_stock",
            "reliable_incoming_quantity",
            "uncovered_quantity",
            "priority",
            "reason_summary",
            "status",
            "assigned_to",
            "resolution_notes",
            "created_at",
            "updated_at",
            "resolved_at",
        )

    def get_active_request(self, obj):
        request = (
            obj.supply_requests.filter(status__in=["OPEN", "PLANNED"])
            .order_by("-id")
            .first()
        )
        if request is None:
            return None
        proposal = (
            request.proposals.exclude(status="REJECTED")
            .select_related("transfer")
            .order_by("-id")
            .first()
        )
        return {
            "id": request.id,
            "status": request.status,
            "status_display": request.get_status_display(),
            "quantity": request.quantity,
            "proposal_status": proposal.status if proposal else None,
            "transfer_id": proposal.transfer_id if proposal else None,
        }


class SupplyGapAssignSerializer(serializers.Serializer):
    assigned_to = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class SupplyGapEscalateSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class SupplyGapResolveSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(required=True, allow_blank=False)
    final_status = serializers.ChoiceField(
        choices=["RESOLVED", "CLOSED"], default="RESOLVED"
    )


class SupplyRequestSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_category = serializers.CharField(
        source="product.category", read_only=True
    )
    unit_of_measure = serializers.CharField(
        source="product.unit_of_measure", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    requested_by_username = serializers.CharField(
        source="requested_by.username", read_only=True, default=None
    )
    open_proposals_count = serializers.SerializerMethodField()

    class Meta:
        model = SupplyRequest
        fields = "__all__"
        read_only_fields = (
            "id",
            "facility",
            "product",
            "quantity",
            "reason",
            "source_recommendation",
            "status",
            "requested_by",
            "created_at",
            "updated_at",
        )

    def get_open_proposals_count(self, obj):
        return getattr(obj, "open_proposals_count", 0)


class SourcingProposalSerializer(serializers.ModelSerializer):
    source_facility_name = serializers.CharField(
        source="source_facility.name", read_only=True
    )
    product_name = serializers.CharField(source="product.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    requesting_facility_name = serializers.CharField(
        source="request.facility.name", read_only=True
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=None
    )
    transfer_id = serializers.IntegerField(
        source="transfer.id", read_only=True, default=None
    )
    transfer_status = serializers.CharField(
        source="transfer.status", read_only=True, default=None
    )

    class Meta:
        model = SourcingProposal
        fields = "__all__"
        read_only_fields = (
            "id",
            "request",
            "recommendation",
            "source_facility",
            "product",
            "quantity",
            "reason",
            "status",
            "transfer",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )


class SupplyRequestCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class SourcingApproveSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class SourcingRejectSerializer(serializers.Serializer):
    note = serializers.CharField(required=True, allow_blank=False)