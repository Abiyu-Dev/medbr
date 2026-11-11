from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    SourcingProposalViewSet,
    SupplyGapReportViewSet,
    SupplyRequestViewSet,
    TransferDeliveryCoordinationViewSet,
)

router = DefaultRouter()
router.register("supply-gaps", SupplyGapReportViewSet, basename="supply-gap")
router.register("supply-requests", SupplyRequestViewSet, basename="supply-request")
router.register(
    "sourcing-proposals", SourcingProposalViewSet, basename="sourcing-proposal"
)

delivery_list_create = TransferDeliveryCoordinationViewSet.as_view(
    {"get": "list", "post": "create"}
)

urlpatterns = [
    path(
        "transfers/<int:transfer_pk>/delivery-coordination/",
        delivery_list_create,
        name="transfer-delivery-coordination",
    ),
    path("central/", include(router.urls)),
]