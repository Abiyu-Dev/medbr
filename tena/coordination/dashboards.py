from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCentralUser
from coordination.models import DeliveryCoordination, SupplyGapReport
from facilities.models import Facility
from inventory.models import StockBatch, TransferRequest
from vaccinations.models import VaccineFollowUp
from ai_engine.models import AIRecommendation
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema


@extend_schema(
    tags=["Dashboards"],
    responses={200: OpenApiTypes.OBJECT},
    description=(
        "Nationwide central summary: facility counts, stock totals, top active "
        "supply gaps, near-expiry redistribution candidates, transfer and "
        "delivery pipeline counts, vaccination follow-up totals, and the "
        "pending AI recommendation queue. Central users only."
    ),
)
class CentralDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsCentralUser]

    def get(self, request):
        today = timezone.localdate()
        now = timezone.now()

        # --- facility counts ---
        facilities = {
            "pending_applications": Facility.objects.filter(
                status="PENDING"
            ).count(),
            "approved": Facility.objects.filter(
                status="APPROVED", is_active=True
            ).count(),
            "suspended": Facility.objects.filter(status="SUSPENDED").count(),
        }

        # --- stock by category (approved + usable) ---
        stock_qs = StockBatch.objects.filter(
            facility__status="APPROVED",
            facility__is_active=True,
            storage_status="OK",
            expiry_date__gte=today,
            quantity_available__gt=0,
        )
        stock_by_cat = {
            row["product__category"]: int(row["total"] or 0)
            for row in stock_qs.values("product__category").annotate(
                total=Sum("quantity_available")
            )
        }
        stock = {
            "medicine_units": stock_by_cat.get("MEDICINE", 0),
            "vaccine_units": stock_by_cat.get("VACCINE", 0),
        }

        # --- top CRITICAL/HIGH gaps ---
        top_gaps_qs = (
            SupplyGapReport.objects.filter(
                status__in=SupplyGapReport.NON_TERMINAL_STATUSES,
                priority__in=["CRITICAL", "HIGH"],
            )
            .select_related("facility", "product")
            .order_by("priority", "-uncovered_quantity")[:20]
        )
        top_gaps = [
            {
                "id": g.id,
                "facility_id": g.facility_id,
                "facility_name": g.facility.name,
                "product_id": g.product_id,
                "product_name": g.product.name,
                "priority": g.priority,
                "uncovered_quantity": g.uncovered_quantity,
                "status": g.status,
                "reporting_horizon_end": g.reporting_horizon_end,
            }
            for g in top_gaps_qs
        ]

        # --- near-expiry redistribution candidates ---
        near_qs = (
            StockBatch.objects.filter(
                facility__status="APPROVED",
                facility__is_active=True,
                storage_status="OK",
                expiry_date__gte=today,
                expiry_date__lte=today + timedelta(days=90),
                quantity_available__gt=0,
            )
            .select_related("facility", "product")
            .order_by("expiry_date")[:20]
        )
        near_redist = [
            {
                "batch_id": b.id,
                "facility_id": b.facility_id,
                "facility_name": b.facility.name,
                "product_id": b.product_id,
                "product_name": b.product.name,
                "batch_number": b.batch_number,
                "quantity_available": b.quantity_available,
                "expiry_date": b.expiry_date,
                "days_until_expiry": (b.expiry_date - today).days,
            }
            for b in near_qs
        ]

        # --- transfer counts ---
        t_map = {
            row["status"]: row["count"]
            for row in TransferRequest.objects.values("status").annotate(
                count=Count("id")
            )
        }
        transfers = {
            "requested": t_map.get("REQUESTED", 0),
            "approved": t_map.get("APPROVED", 0),
            "dispatched": t_map.get("DISPATCHED", 0),
            "in_transit": t_map.get("IN_TRANSIT", 0),
            "received": t_map.get("RECEIVED", 0),
            "recent_7d": TransferRequest.objects.filter(
                created_at__gte=now - timedelta(days=7)
            ).count(),
        }

        # --- supply gaps ---
        sg_map = {
            row["status"]: row["count"]
            for row in SupplyGapReport.objects.values("status").annotate(
                count=Count("id")
            )
        }
        supply_gaps = {
            "open": sg_map.get("OPEN", 0),
            "under_review": sg_map.get("UNDER_REVIEW", 0),
            "assigned": sg_map.get("ASSIGNED", 0),
            "action_planned": sg_map.get("ACTION_PLANNED", 0),
            "escalated": sg_map.get("ESCALATED", 0),
            "resolved": sg_map.get("RESOLVED", 0),
            "closed": sg_map.get("CLOSED", 0),
            "critical_active": SupplyGapReport.objects.filter(
                status__in=SupplyGapReport.NON_TERMINAL_STATUSES,
                priority="CRITICAL",
            ).count(),
            "high_active": SupplyGapReport.objects.filter(
                status__in=SupplyGapReport.NON_TERMINAL_STATUSES,
                priority="HIGH",
            ).count(),
        }

        # --- deliveries ---
        d_map = {
            row["delivery_status"]: row["count"]
            for row in DeliveryCoordination.objects.values(
                "delivery_status"
            ).annotate(count=Count("id"))
        }
        deliveries = {
            "arranged_by_phone": d_map.get("ARRANGED_BY_PHONE", 0),
            "dispatched": d_map.get("DISPATCHED", 0),
            "received": d_map.get("RECEIVED", 0),
            "discrepancy": d_map.get("DISCREPANCY", 0),
            "failed": d_map.get("FAILED", 0),
        }

        # --- vaccination follow-ups ---
        vaccinations = {
            "due_7d": VaccineFollowUp.objects.filter(
                patient__active=True,
                due_date__gte=today,
                due_date__lte=today + timedelta(days=7),
                status__in=["UPCOMING", "DUE"],
            ).count(),
            "overdue": VaccineFollowUp.objects.filter(
                patient__active=True,
                due_date__lt=today,
                status__in=[
                    "UPCOMING",
                    "DUE",
                    "OVERDUE",
                    "CONTACT_ATTEMPTED",
                ],
            ).count(),
        }

        # --- AI recommendation queue (added in M8) ---
        pending_ai = (
            AIRecommendation.objects.filter(
                status=AIRecommendation.Status.PENDING_REVIEW
            )
            .select_related("scope_facility")
            .order_by("-created_at")[:10]
        )
        ai_queue = [
            {
                "id": r.id,
                "analysis_type": r.analysis_type,
                "scope_facility_id": r.scope_facility_id,
                "scope_facility_name": (
                    r.scope_facility.name if r.scope_facility else None
                ),
                "summary": r.summary,
                "created_at": r.created_at,
                "validation_error_count": len(r.validation_errors or []),
            }
            for r in pending_ai
        ]

        return Response(
            {
                "as_of": today,
                "facilities": facilities,
                "stock": stock,
                "top_gaps": top_gaps,
                "near_expiry_redistribution": near_redist,
                "transfers": transfers,
                "supply_gaps": supply_gaps,
                "deliveries": deliveries,
                "vaccinations": vaccinations,
                "ai_recommendations": {
                    "pending_review": AIRecommendation.objects.filter(
                        status=AIRecommendation.Status.PENDING_REVIEW
                    ).count(),
                    "failed_last_7_days": AIRecommendation.objects.filter(
                        status=AIRecommendation.Status.FAILED,
                        created_at__gte=now - timedelta(days=7),
                    ).count(),
                    "queue": ai_queue,
                },
            }
        )