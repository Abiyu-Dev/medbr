from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DueFollowUpsView,
    OverdueFollowUpsView,
    PatientViewSet,
    VaccinationRecordViewSet,
    VaccinesListView,
    VaccineFollowUpViewSet,
    VaccineScheduleViewSet,
)

router = DefaultRouter()
router.register("patients", PatientViewSet, basename="patient")
router.register("vaccination-schedules", VaccineScheduleViewSet, basename="vaccination-schedule")
router.register("vaccination-records", VaccinationRecordViewSet, basename="vaccination-record")
router.register("vaccination-followups", VaccineFollowUpViewSet, basename="vaccination-followup")

urlpatterns = [
    path("vaccines/", VaccinesListView.as_view(), name="vaccines"),
    path("vaccinations/due/", DueFollowUpsView.as_view(), name="vaccinations-due"),
    path("vaccinations/overdue/", OverdueFollowUpsView.as_view(), name="vaccinations-overdue"),
    path("", include(router.urls)),
]