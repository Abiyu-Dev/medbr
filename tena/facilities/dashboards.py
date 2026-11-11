from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AuditLog
from accounts.serializers import AuditLogSerializer
from facilities.serializers import FacilitySerializer
from inventory.calculations import (
    get_facility_product_ids,
    get_near_expiry_batches,
    get_product_summary,
)
from inventory.models import *
from inventory.serializers import StockMovementSerializer
from inventory.views import _resolve_facility  # reuse scope resolution from M4
from vaccinations.models import VaccineFollowUp
from vaccinations.services import sync_follow_up_statuses

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema


OPEN_TRANSFER_STATUSES = [
    "REQUESTED",
    "UNDER_REVIEW",
    "APPROVED",
    "DISPATCHED",
    "IN_TRANSIT",
]

@extend_schema(
    tags=["Dashboards"],
    responses={200: OpenApiTypes.OBJECT},
    description=(
        "Facility-scoped operational summary: inventory, shortages, near-expiry, "
        "transfers, vaccinations, equipment, recent movements, audit activity, "
        "and data freshness. Central users must pass `?facility=<id>`."
    ),
)
class FacilityDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility, err = _resolve_facility(request)
        if err:
            return err

        today = timezone.localdate()

        # --- facility profile ---
        facility_data = FacilitySerializer(facility).data

        # --- inventory aggregates ---
        usable_qs = StockBatch.objects.filter(
            facility=facility,
            storage_status=StockBatch.StorageStatus.OK,
            expiry_date__gte=today,
            quantity_available__gt=0,
        )
        usable_units = int(usable_qs.aggregate(s=Sum("quantity_available"))["s"] or 0)
        total_batches = StockBatch.objects.filter(facility=facility).count()

        # --- shortages ---
        product_ids = get_facility_product_ids(facility, as_of=today)
        products = Product.objects.filter(id__in=product_ids, active=True)

        all_shortages = []
        for product in products:
            summary = get_product_summary(
                facility, product, horizon_days=30, as_of=today
            )
            if summary["projected_gap"] is not None and summary["projected_gap"] > 0:
                all_shortages.append(summary)
        all_shortages.sort(key=lambda r: (-r["projected_gap"], r["product_name"]))

        products_with_gap = len(all_shortages)
        critical_shortages = len(
            [
                s
                for s in all_shortages
                if s["days_of_stock"] is not None and s["days_of_stock"] < 7
            ]
        )
        shortages = all_shortages[:10]

        # --- near expiry ---
        near_qs = get_near_expiry_batches(facility, days=90, as_of=today)[:10]
        near_expiry = [
            {
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "product_id": b.product_id,
                "product_name": b.product.name,
                "quantity_available": b.quantity_available,
                "expiry_date": b.expiry_date,
                "days_until_expiry": (b.expiry_date - today).days,
            }
            for b in near_qs
        ]

        # --- transfers (open only) ---
        incoming_qs = (
            TransferRequest.objects.filter(
                destination_facility=facility,
                status__in=OPEN_TRANSFER_STATUSES,
            )
            .select_related("source_facility", "product")
            .order_by("-created_at")[:10]
        )
        outgoing_qs = (
            TransferRequest.objects.filter(
                source_facility=facility,
                status__in=OPEN_TRANSFER_STATUSES,
            )
            .select_related("destination_facility", "product")
            .order_by("-created_at")[:10]
        )

        def _transfer_row(t, peer_attr):
            peer = getattr(t, peer_attr)
            return {
                "id": t.id,
                "peer_facility_id": peer.id,
                "peer_facility_name": peer.name,
                "product_id": t.product_id,
                "product_name": t.product.name,
                "quantity_requested": t.quantity_requested,
                "quantity_approved": t.quantity_approved,
                "status": t.status,
                "priority": t.priority,
                "expected_arrival_at": t.expected_arrival_at,
            }

        incoming = [_transfer_row(t, "source_facility") for t in incoming_qs]
        outgoing = [_transfer_row(t, "destination_facility") for t in outgoing_qs]

        # --- vaccinations ---
        if facility.provides_vaccination_services:
            sync_follow_up_statuses(facility, today=today)
            due_count = VaccineFollowUp.objects.filter(
                patient__facility=facility,
                patient__active=True,
                due_date__gte=today,
                due_date__lte=today + timedelta(days=7),
                status__in=["UPCOMING", "DUE"],
            ).count()
            overdue_count = VaccineFollowUp.objects.filter(
                patient__facility=facility,
                patient__active=True,
                due_date__lt=today,
                status__in=["UPCOMING", "DUE", "OVERDUE", "CONTACT_ATTEMPTED"],
            ).count()
        else:
            due_count = 0
            overdue_count = 0

        # --- equipment ---
        eq_qs = Equipment.objects.filter(facility=facility)
        equipment = {
            "total": eq_qs.count(),
            "out_of_service": eq_qs.filter(condition="OUT_OF_SERVICE").count(),
            "needs_maintenance": eq_qs.filter(condition="NEEDS_MAINTENANCE").count(),
        }

        # --- recent movements & audit ---
        recent_mv = (
            StockMovement.objects.filter(batch__facility=facility)
            .select_related("batch", "batch__product", "performed_by")
            .order_by("-created_at")[:10]
        )
        recent_audit_qs = (
            AuditLog.objects.filter(
                Q(actor__facility_id=facility.id)
                | Q(entity_type="Facility", entity_id=str(facility.id))
            )
            .select_related("actor")
            .order_by("-created_at")[:10]
        )

        # --- data freshness ---
        last_movement_at = (
            StockMovement.objects.filter(batch__facility=facility)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        last_audit_at = (
            AuditLog.objects.filter(actor__facility_id=facility.id)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )

        return Response(
            {
                "facility": facility_data,
                "as_of": today,
                "inventory": {
                    "total_batches": total_batches,
                    "usable_units": usable_units,
                    "products_with_gap": products_with_gap,
                    "critical_shortages": critical_shortages,
                },
                "shortages": shortages,
                "near_expiry": near_expiry,
                "transfers": {
                    "incoming": incoming,
                    "outgoing": outgoing,
                },
                "vaccinations": {
                    "due_in_7_days": due_count,
                    "overdue": overdue_count,
                },
                "equipment": equipment,
                "recent_movements": StockMovementSerializer(
                    recent_mv, many=True
                ).data,
                "recent_audit": AuditLogSerializer(
                    recent_audit_qs, many=True
                ).data,
                "data_freshness": {
                    "last_stock_movement_at": last_movement_at,
                    "last_audit_at": last_audit_at,
                },
            }
        )