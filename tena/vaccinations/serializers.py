from datetime import date

from rest_framework import serializers

from inventory.models import Product, StockBatch

from .models import Patient, VaccinationRecord, VaccineFollowUp, VaccineSchedule


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------


class PatientSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    sex_display = serializers.CharField(source="get_sex_display", read_only=True)

    class Meta:
        model = Patient
        fields = "__all__"
        read_only_fields = (
            "id",
            "facility",
            "facility_name",
            "sex_display",
            "created_by",
            "created_at",
            "updated_at",
        )


class PatientCreateSerializer(serializers.ModelSerializer):
    patient_number = serializers.CharField(
        required=False, allow_blank=True, max_length=32
    )
    class Meta:
        model = Patient
        fields = (
            "patient_number",
            "full_name",
            "date_of_birth",
            "sex",
            "guardian_name",
            "guardian_phone",
            "patient_phone",
            "address_area",
            "consent_given",
            "consent_date",
        )

    def validate_patient_number(self, value):
        if value and Patient.objects.filter(
            facility=self.context["facility"], patient_number=value
        ).exists():
            raise serializers.ValidationError(
                "Patient number already in use at this facility."
            )
        return value

    def validate_date_of_birth(self, value):
        if value > date.today():
            raise serializers.ValidationError("Cannot be in the future.")
        return value


class PatientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = (
            "full_name",
            "guardian_name",
            "guardian_phone",
            "patient_phone",
            "address_area",
            "consent_given",
            "consent_date",
            "active",
        )


# ---------------------------------------------------------------------------
# VaccineSchedule
# ---------------------------------------------------------------------------


class VaccineScheduleSerializer(serializers.ModelSerializer):
    vaccine_product_name = serializers.CharField(
        source="vaccine_product.name", read_only=True
    )

    class Meta:
        model = VaccineSchedule
        fields = "__all__"
        read_only_fields = (
            "id",
            "approved_by",
            "created_at",
            "updated_at",
        )


class VaccineScheduleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VaccineSchedule
        fields = (
            "vaccine_product",
            "dose_number",
            "recommended_age_days",
            "recommended_age_label",
            "minimum_interval_days",
            "effective_from",
            "source_name",
            "source_version",
            "active",
        )

    def validate_vaccine_product(self, value):
        if value.category != Product.Category.VACCINE:
            raise serializers.ValidationError("Product must have category VACCINE.")
        return value

    def validate(self, attrs):
        if (
            attrs.get("recommended_age_days") is None
            and attrs.get("minimum_interval_days") is None
        ):
            raise serializers.ValidationError(
                "At least one of recommended_age_days or minimum_interval_days "
                "must be set."
            )
        return attrs


# ---------------------------------------------------------------------------
# VaccinationRecord
# ---------------------------------------------------------------------------


class VaccinationRecordSerializer(serializers.ModelSerializer):
    patient_number = serializers.CharField(
        source="patient.patient_number", read_only=True
    )
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    vaccine_product_name = serializers.CharField(
        source="vaccine_product.name", read_only=True
    )
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    recorded_by_username = serializers.CharField(
        source="recorded_by.username", read_only=True, default=None
    )
    schedule_id = serializers.IntegerField(source="schedule.id", read_only=True)

    class Meta:
        model = VaccinationRecord
        fields = "__all__"
        read_only_fields = (
            "id",
            "schedule",
            "schedule_id",
            "facility",
            "facility_name",
            "recorded_by",
            "recorded_by_username",
            "created_at",
            "patient_number",
            "patient_name",
            "vaccine_product_name",
            "batch_number",
        )


class VaccinationRecordCreateSerializer(serializers.Serializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())
    vaccine_product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(category=Product.Category.VACCINE, active=True)
    )
    dose_number = serializers.IntegerField(min_value=1)
    administered_at = serializers.DateTimeField()
    batch = serializers.PrimaryKeyRelatedField(
        queryset=StockBatch.objects.all()
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and getattr(request.user, "facility_id", None):
            self.fields["patient"].queryset = Patient.objects.filter(
                facility_id=request.user.facility_id
            )
            self.fields["batch"].queryset = StockBatch.objects.filter(
                facility_id=request.user.facility_id
            )


# ---------------------------------------------------------------------------
# VaccineFollowUp
# ---------------------------------------------------------------------------


class VaccineFollowUpSerializer(serializers.ModelSerializer):
    patient_number = serializers.CharField(
        source="patient.patient_number", read_only=True
    )
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    vaccine_product_name = serializers.CharField(
        source="vaccine_product.name", read_only=True
    )
    assigned_to_username = serializers.CharField(
        source="assigned_to.username", read_only=True, default=None
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    contact_outcome_display = serializers.CharField(
        source="get_contact_outcome_display", read_only=True
    )
    effective_status = serializers.SerializerMethodField()

    class Meta:
        model = VaccineFollowUp
        fields = "__all__"
        read_only_fields = (
            "id",
            "status",
            "status_display",
            "last_contacted_at",
            "contact_outcome",
            "review_reason",
            "created_at",
            "updated_at",
            "patient_number",
            "patient_name",
            "vaccine_product_name",
            "assigned_to_username",
            "contact_outcome_display",
            "effective_status",
        )

    def get_effective_status(self, obj):
        return obj.effective_status()


class VaccineFollowUpCreateSerializer(serializers.Serializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())
    vaccine_product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(category=Product.Category.VACCINE, active=True)
    )
    dose_number = serializers.IntegerField(min_value=1)
    due_date = serializers.DateField()
    assigned_to = serializers.IntegerField(required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and getattr(request.user, "facility_id", None):
            self.fields["patient"].queryset = Patient.objects.filter(
                facility_id=request.user.facility_id
            )


class ContactFollowUpSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(
        choices=VaccineFollowUp.ContactOutcome.choices
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    next_action_date = serializers.DateField(required=False, allow_null=True)


class MarkReviewRequiredSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)


class CancelFollowUpSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")