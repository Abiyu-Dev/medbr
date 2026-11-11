from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.calculations import get_product_summary
from inventory.models import Product, StockBatch, TransferRequest
from inventory.transfers import create_transfer_request

from .models import SourcingProposal, SupplyGapReport, SupplyRequest


class SourcingError(Exception):
    """Raised on sourcing rule violations. Mapped to HTTP 409 by views."""


def _derive_priority(days_of_stock, projected_gap, projected_demand):
    if projected_gap is None or projected_gap <= 0:
        return None
    if days_of_stock is None or days_of_stock <= 0:
        return SupplyGapReport.Priority.CRITICAL
    if days_of_stock < 7:
        return SupplyGapReport.Priority.CRITICAL
    if days_of_stock < 14:
        return SupplyGapReport.Priority.HIGH
    if days_of_stock < 30:
        return SupplyGapReport.Priority.MEDIUM
    return SupplyGapReport.Priority.LOW


def _build_reason_summary(summary):
    parts = [
        f"Projected demand {summary['projected_demand']} over horizon;",
        f"usable stock {summary['usable_stock']};",
        f"reliable incoming {summary['incoming_stock']};",
        f"uncovered {summary['projected_gap']}.",
    ]
    if summary["days_of_stock"] is not None:
        parts.append(f"Days of stock: {summary['days_of_stock']}.")
    return " ".join(parts)


@transaction.atomic
def upsert_supply_gap(
    *,
    facility,
    product,
    horizon_days=30,
    usage_window_days=30,
    summary=None,
):
    """
    Create or update the single active gap report for (facility, product).
    Returns (report_or_None, created_bool).
    """
    if summary is None:
        summary = get_product_summary(
            facility,
            product,
            horizon_days=horizon_days,
            usage_window_days=usage_window_days,
        )

    priority = _derive_priority(
        summary["days_of_stock"],
        summary["projected_gap"],
        summary["projected_demand"],
    )
    if priority is None:
        return None, False

    today = timezone.localdate()
    horizon_end = today + timedelta(days=horizon_days)

    existing = (
        SupplyGapReport.objects.select_for_update()
        .filter(
            facility=facility,
            product=product,
            status__in=SupplyGapReport.NON_TERMINAL_STATUSES,
        )
        .first()
    )

    if existing:
        existing.reporting_horizon_start = today
        existing.reporting_horizon_end = horizon_end
        existing.projected_demand = summary["projected_demand"]
        existing.usable_stock = summary["usable_stock"]
        existing.reliable_incoming_quantity = summary["incoming_stock"]
        existing.uncovered_quantity = summary["projected_gap"]
        existing.priority = priority
        existing.reason_summary = _build_reason_summary(summary)
        existing.save()
        return existing, False

    report = SupplyGapReport.objects.create(
        facility=facility,
        product=product,
        reporting_horizon_start=today,
        reporting_horizon_end=horizon_end,
        projected_demand=summary["projected_demand"],
        usable_stock=summary["usable_stock"],
        reliable_incoming_quantity=summary["incoming_stock"],
        uncovered_quantity=summary["projected_gap"],
        priority=priority,
        reason_summary=_build_reason_summary(summary),
        status=SupplyGapReport.Status.OPEN,
    )
    return report, True


def refresh_supply_gaps(*, facility=None, horizon_days=30, usage_window_days=30):
    """
    Iterate every (facility, product) that has batches and upsert its open gap.
    Returns (created, updated).
    """
    from facilities.models import Facility

    facilities = Facility.objects.filter(status="APPROVED", is_active=True)
    if facility is not None:
        facilities = facilities.filter(pk=facility.pk)

    created_count = 0
    updated_count = 0
    for fac in facilities:
        product_ids = set(
            StockBatch.objects.filter(facility=fac).values_list(
                "product_id", flat=True
            )
        )
        products = Product.objects.filter(id__in=product_ids, active=True)
        for product in products:
            report, was_created = upsert_supply_gap(
                facility=fac,
                product=product,
                horizon_days=horizon_days,
                usage_window_days=usage_window_days,
            )
            if report is None:
                continue
            if was_created:
                created_count += 1
            else:
                updated_count += 1
    return created_count, updated_count


# ---------------------------------------------------------------------------
# Sourcing proposals (central review of AI-planned donor transfers)
# ---------------------------------------------------------------------------


def _pick_fefo_batch(source_facility, product, quantity):
    cutoff = timezone.localdate() + timedelta(
        days=settings.AI_MIN_REMAINING_SHELF_LIFE_DAYS
    )
    candidates = StockBatch.objects.select_for_update().filter(
        facility=source_facility,
        product=product,
        storage_status=StockBatch.StorageStatus.OK,
        expiry_date__gte=cutoff,
        quantity_available__gt=F("quantity_reserved"),
    ).order_by("expiry_date", "id")
    for batch in candidates:
        if batch.quantity_available - batch.quantity_reserved >= quantity:
            return batch
    return None


@transaction.atomic
def cancel_supply_request(*, request, cancelled_by, reason=""):
    locked = SupplyRequest.objects.select_for_update().get(pk=request.pk)
    if locked.status not in (
        SupplyRequest.Status.OPEN,
        SupplyRequest.Status.PLANNED,
    ):
        raise SourcingError(
            f"Cannot cancel a supply request in status {locked.status}."
        )
    locked.status = SupplyRequest.Status.CANCELLED
    if reason:
        locked.reason = (locked.reason + "\n" if locked.reason else "") + (
            f"Cancelled: {reason}"
        )
    locked.save(update_fields=["status", "reason", "updated_at"])
    return locked


@transaction.atomic
def approve_sourcing_proposal(*, proposal, reviewed_by, note=""):
    locked = (
        SourcingProposal.objects.select_for_update()
        .select_related("request", "request__facility", "source_facility", "product")
        .get(pk=proposal.pk)
    )
    if locked.status != SourcingProposal.Status.PROPOSED:
        raise SourcingError(f"Proposal is already {locked.status}.")
    req = SupplyRequest.objects.select_for_update().get(pk=locked.request_id)
    if req.status != SupplyRequest.Status.OPEN:
        raise SourcingError(
            f"Supply request is {req.status}; only OPEN requests can be planned."
        )

    product = locked.product
    if product.requires_cold_chain and not locked.source_facility.has_cold_chain:
        raise SourcingError("Source facility lacks cold chain for this product.")
    batch = _pick_fefo_batch(locked.source_facility, product, locked.quantity)
    if batch is None:
        raise SourcingError(
            "No usable source batch with sufficient shelf life and free stock."
        )

    transfer = create_transfer_request(
        source_facility=locked.source_facility,
        destination_facility=req.facility,
        product=product,
        source_batch=batch,
        quantity_requested=locked.quantity,
        priority=TransferRequest.Priority.HIGH,
        requested_by=reviewed_by,
        notes=(
            f"Auto-sourced for supply request #{req.id} "
            f"(AI proposal #{locked.id}): {locked.reason}"
        ),
    )

    now = timezone.now()
    locked.status = SourcingProposal.Status.APPROVED
    locked.transfer = transfer
    locked.reviewed_by = reviewed_by
    locked.reviewed_at = now
    if note:
        locked.review_note = note
    locked.save()

    req.status = SupplyRequest.Status.PLANNED
    req.save(update_fields=["status", "updated_at"])

    SourcingProposal.objects.filter(
        request=req, status=SourcingProposal.Status.PROPOSED
    ).exclude(pk=locked.pk).update(
        status=SourcingProposal.Status.REJECTED,
        review_note=f"Superseded by approved proposal #{locked.id}.",
        reviewed_by=reviewed_by,
        reviewed_at=now,
    )
    return locked, transfer


@transaction.atomic
def reject_sourcing_proposal(*, proposal, reviewed_by, note):
    if not note or not note.strip():
        raise SourcingError("A rejection note is required.")
    locked = SourcingProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status != SourcingProposal.Status.PROPOSED:
        raise SourcingError(f"Proposal is already {locked.status}.")
    locked.status = SourcingProposal.Status.REJECTED
    locked.review_note = note
    locked.reviewed_by = reviewed_by
    locked.reviewed_at = timezone.now()
    locked.save()
    return locked