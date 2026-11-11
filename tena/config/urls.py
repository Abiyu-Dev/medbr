from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from accounts.audit_views import AuditLogViewSet
from coordination.dashboards import CentralDashboardSummaryView
from facilities.dashboards import FacilityDashboardSummaryView


audit_list = AuditLogViewSet.as_view({"get": "list"})
audit_detail = AuditLogViewSet.as_view({"get": "retrieve"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/facilities/", include("facilities.urls")),
    path("api/v1/", include("inventory.urls")),
    path("api/v1/", include("coordination.urls")),
    path("api/v1/", include("vaccinations.urls")),
    path("api/v1/ai/", include("ai_engine.urls")),
    path(
        "api/v1/dashboard/facility-summary/",
        FacilityDashboardSummaryView.as_view(),
        name="dashboard-facility-summary",
    ),
    path(
        "api/v1/dashboard/central-summary/",
        CentralDashboardSummaryView.as_view(),
        name="dashboard-central-summary",
    ),
    path("api/v1/audit/logs/", audit_list, name="audit-logs"),
    path("api/v1/audit/logs/<int:pk>/", audit_detail, name="audit-log-detail"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]