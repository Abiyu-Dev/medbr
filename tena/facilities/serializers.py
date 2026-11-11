from rest_framework import serializers

from .models import Facility


def _validate_coords(attrs):
    lat = attrs.get("latitude")
    lon = attrs.get("longitude")
    if lat is not None and not (-90 <= float(lat) <= 90):
        raise serializers.ValidationError({"latitude": "Must be between -90 and 90."})
    if lon is not None and not (-180 <= float(lon) <= 180):
        raise serializers.ValidationError({"longitude": "Must be between -180 and 180."})
    return attrs


class FacilitySerializer(serializers.ModelSerializer):
    submitted_by_username = serializers.CharField(
        source="submitted_by.username", read_only=True, default=None
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=None
    )
    facility_type_display = serializers.CharField(
        source="get_facility_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Facility
        fields = "__all__"
        read_only_fields = (
            "id",
            "status",
            "is_active",
            "submitted_by",
            "submitted_by_username",
            "reviewed_by",
            "reviewed_by_username",
            "reviewed_at",
            "review_note",
            "created_at",
            "updated_at",
        )


class FacilityApplicationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = (
            "name",
            "facility_type",
            "registration_number",
            "region",
            "zone",
            "woreda",
            "kebele",
            "town",
            "address",
            "landmark",
            "latitude",
            "longitude",
            "contact_phone",
            "contact_email",
            "storage_capacity_notes",
            "has_cold_chain",
            "cold_chain_notes",
            "provides_vaccination_services",
        )

    def validate(self, attrs):
        return _validate_coords(attrs)


class FacilityUpdateSerializer(serializers.ModelSerializer):
    """
    Used by facility managers / admins to edit an approved facility's operational profile.
    facility_type, registration_number, and status are intentionally not editable here.
    """

    class Meta:
        model = Facility
        fields = (
            "name",
            "address",
            "landmark",
            "latitude",
            "longitude",
            "contact_phone",
            "contact_email",
            "storage_capacity_notes",
            "has_cold_chain",
            "cold_chain_notes",
        )

    def validate(self, attrs):
        return _validate_coords(attrs)


class FacilityRejectSerializer(serializers.Serializer):
    review_note = serializers.CharField(required=True, allow_blank=False)


class FacilitySuspendSerializer(serializers.Serializer):
    review_note = serializers.CharField(required=False, allow_blank=True, default="")