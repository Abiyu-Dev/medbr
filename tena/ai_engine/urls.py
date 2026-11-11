from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AIRecommendationViewSet,
    AnalyzeInventoryView,
    PlanGapSourcingView,
    PlanTransferSourcingView,
    PrioritizeSupplyGapsView,
    SummarizeVaccinationDemandView,
)

router = DefaultRouter()
router.register("recommendations", AIRecommendationViewSet, basename="ai-recommendation")

urlpatterns = [
    path(
        "analyze-inventory/",
        AnalyzeInventoryView.as_view(),
        name="ai-analyze-inventory",
    ),
    path(
        "prioritize-supply-gaps/",
        PrioritizeSupplyGapsView.as_view(),
        name="ai-prioritize-supply-gaps",
    ),
    path(
        "summarize-vaccination-demand/",
        SummarizeVaccinationDemandView.as_view(),
        name="ai-summarize-vaccination-demand",
    ),
    path(
        "plan-transfer-sourcing/",
        PlanTransferSourcingView.as_view(),
        name="ai-plan-transfer-sourcing",
    ),
    path(
        "plan-gap-sourcing/",
        PlanGapSourcingView.as_view(),
        name="ai-plan-gap-sourcing",
    ),
    path("", include(router.urls)),
]