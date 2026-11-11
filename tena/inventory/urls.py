from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import *

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("batches", StockBatchViewSet, basename="batch")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("equipment", EquipmentViewSet, basename="equipment")
router.register("transfers", TransferRequestViewSet, basename="transfer")

urlpatterns = [
    path("stock-receipts/", StockReceiptView.as_view(), name="stock-receipts"),
    path("stock-consumption/", StockConsumptionView.as_view(), name="stock-consumption"),
    path("stock-wastage/", StockWastageView.as_view(), name="stock-wastage"),
    path("stock-adjustments/", StockAdjustmentView.as_view(), name="stock-adjustments"),
    path("inventory/summary/", InventorySummaryView.as_view(), name="inventory-summary"),
    path("inventory/shortages/", InventoryShortagesView.as_view(), name="inventory-shortages"),
    path("inventory/expiring/", InventoryExpiringView.as_view(), name="inventory-expiring"),
    path("", include(router.urls)),
]