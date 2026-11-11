from django.contrib import admin

from .models import Patient, VaccinationRecord, VaccineFollowUp, VaccineSchedule


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("patient_number", "full_name", "facility", "sex", "active")
    list_filter = ("facility", "active", "sex")
    search_fields = ("patient_number", "full_name", "patient_phone", "guardian_phone")


@admin.register(VaccineSchedule)
class VaccineScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "vaccine_product",
        "dose_number",
        "recommended_age_days",
        "minimum_interval_days",
        "active",
        "effective_from",
    )
    list_filter = ("active", "vaccine_product")
    search_fields = ("vaccine_product__name", "source_name")


@admin.register(VaccinationRecord)
class VaccinationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "vaccine_product",
        "dose_number",
        "administered_at",
        "facility",
        "recorded_by",
    )
    list_filter = ("facility", "vaccine_product")
    search_fields = ("patient__full_name", "patient__patient_number")


@admin.register(VaccineFollowUp)
class VaccineFollowUpAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "vaccine_product",
        "dose_number",
        "due_date",
        "status",
        "assigned_to",
    )
    list_filter = ("status", "vaccine_product")
    search_fields = ("patient__full_name", "patient__patient_number")