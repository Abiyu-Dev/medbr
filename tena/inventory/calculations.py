from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone
from django.db.models import F, Sum
from django.db import models
from .models import Product, StockBatch, StockMovement
from django.db.models import Q, Sum  # ensure Q, Sum present

_ACTIVE_OUT_TYPES = [
    StockMovement.MovementType.CONSUMPTION,
    StockMovement.MovementType.VACCINATION_ADMINISTRATION,
]


def get_follow_up_demand_in_horizon(facility, product, horizon_days=30, as_of=None):
    """
    Count of open (not COMPLETED/CANCELLED) follow-ups whose due_date falls in
    [today, today + horizon_days] for this product at this facility.
    Lazy import avoids import cycles.
    """
    from vaccinations.models import VaccineFollowUp

    as_of = as_of or timezone.localdate()
    horizon_end = as_of + timedelta(days=horizon_days)

    qs = VaccineFollowUp.objects.filter(
        patient__facility=facility,
        patient__active=True,
        vaccine_product=product,
        due_date__gte=as_of,
        due_date__lte=horizon_end,
    ).exclude(
        status__in=[
            VaccineFollowUp.Status.COMPLETED,
            VaccineFollowUp.Status.CANCELLED,
        ]
    )
    return qs.count()

def get_usable_stock(facility, product, as_of=None):
    """
    Stock that is physically OK, not expired, and not committed to another
    approved transfer (i.e. available for allocation).
    """
    as_of = as_of or timezone.localdate()
    batches = StockBatch.objects.filter(
        facility=facility,
        product=product,
        storage_status=StockBatch.StorageStatus.OK,
        expiry_date__gte=as_of,
        quantity_available__gt=0,
    )
    return sum(
        max(0, b.quantity_available - b.quantity_reserved) for b in batches
    )


def get_incoming_stock(facility, product, horizon_days=30, as_of=None):
    """
    Confirmed (approved/dispatched/in-transit) transfers headed to this facility.
    Unapproved or rejected transfers are NOT counted.
    """
    from .models import TransferRequest

    as_of = as_of or timezone.localdate()
    horizon_end = as_of + timedelta(days=horizon_days)

    qs = TransferRequest.objects.filter(
        destination_facility=facility,
        product=product,
        status__in=[
            TransferRequest.Status.APPROVED,
            TransferRequest.Status.DISPATCHED,
            TransferRequest.Status.IN_TRANSIT,
        ],
    ).filter(
        models.Q(expected_arrival_at__isnull=True)
        | models.Q(expected_arrival_at__date__lte=horizon_end)
    )
    return int(qs.aggregate(total=Sum("quantity_approved"))["total"] or 0)


def get_reserved_stock(facility, product):
    from django.db.models import Sum

    total = StockBatch.objects.filter(facility=facility, product=product).aggregate(
        total=Sum("quantity_reserved")
    )["total"]
    return int(total or 0)


def get_estimated_daily_usage(facility, product, window_days=30, as_of=None):
    """
    Average daily OUT usage over the recent window.
    Wastage is NOT demand and is excluded.
    Returns Decimal or None when no usage history exists.
    """
    from django.db.models import Sum

    as_of = as_of or timezone.localdate()
    start = as_of - timedelta(days=window_days)

    total = (
        StockMovement.objects.filter(
            batch__facility=facility,
            batch__product=product,
            occurred_at__date__gte=start,
            occurred_at__date__lte=as_of,
            direction=StockMovement.Direction.OUT,
            movement_type__in=_ACTIVE_OUT_TYPES,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    if total == 0:
        return None
    return (Decimal(total) / Decimal(window_days)).quantize(Decimal("0.0001"))


def get_near_expiry_batches(facility, days=90, product=None, as_of=None):
    """
    Usable batches whose expiry falls within the threshold.
    Already-expired batches are deliberately excluded.
    """
    as_of = as_of or timezone.localdate()
    cutoff = as_of + timedelta(days=days)
    qs = StockBatch.objects.select_related("product").filter(
        facility=facility,
        storage_status=StockBatch.StorageStatus.OK,
        expiry_date__gte=as_of,
        expiry_date__lte=cutoff,
        quantity_available__gt=0,
    )
    if product is not None:
        qs = qs.filter(product=product)
    return qs.order_by("expiry_date")


def get_product_summary(
    facility,
    product,
    horizon_days=30,
    near_expiry_days=90,
    usage_window_days=30,
    as_of=None,
):
    as_of = as_of or timezone.localdate()

    usable = get_usable_stock(facility, product, as_of)
    reserved = get_reserved_stock(facility, product)
    incoming = get_incoming_stock(facility, product, horizon_days, as_of)
    daily = get_estimated_daily_usage(facility, product, usage_window_days, as_of)
    follow_up_demand = get_follow_up_demand_in_horizon(
        facility, product, horizon_days, as_of
    )

    historical_demand = None
    if daily is not None:
        historical_demand = int(
            (daily * horizon_days).to_integral_value(rounding=ROUND_CEILING)
        )

    if historical_demand is None and follow_up_demand == 0:
        projected_demand = None
        projected_gap = None
        days_of_stock = None
        daily_float = None
    else:
        projected_demand = max(historical_demand or 0, follow_up_demand)
        projected_gap = max(0, projected_demand - usable - incoming)
        if daily is not None and daily > 0:
            days_of_stock = round(float(usable) / float(daily), 2)
        else:
            days_of_stock = 0.0 if projected_demand and usable == 0 else None
        daily_float = float(daily) if daily is not None else None

    near_batches = list(
        get_near_expiry_batches(facility, near_expiry_days, product, as_of)
    )
    near_qty = sum(b.quantity_available for b in near_batches)

    batch_count = StockBatch.objects.filter(
        facility=facility, product=product, quantity_available__gt=0
    ).count()

    return {
        "product_id": product.id,
        "product_name": product.name,
        "category": product.category,
        "unit_of_measure": product.unit_of_measure,
        "usable_stock": usable,
        "reserved_stock": reserved,
        "incoming_stock": incoming,
        "projected_demand": projected_demand,
        "projected_gap": projected_gap,
        "days_of_stock": days_of_stock,
        "estimated_daily_usage": daily_float,
        "follow_up_demand": follow_up_demand,
        "near_expiry_quantity": int(near_qty),
        "batch_count": batch_count,
    }


def get_facility_product_ids(facility, usage_window_days=30, as_of=None):
    """
    Products the facility actually deals with:
    - has at least one batch here
    - had CONSUMPTION / VACCINATION_ADMINISTRATION usage in the recent window
    - has open vaccination follow-ups (added M6)
    - has an approved/dispatched/in-transit transfer headed here (added M5)
    """
    from vaccinations.models import VaccineFollowUp
    from .models import TransferRequest

    as_of = as_of or timezone.localdate()
    start = as_of - timedelta(days=usage_window_days)

    batch_ids = set(
        StockBatch.objects.filter(facility=facility).values_list(
            "product_id", flat=True
        )
    )
    usage_ids = set(
        StockMovement.objects.filter(
            batch__facility=facility,
            occurred_at__date__gte=start,
            occurred_at__date__lte=as_of,
            direction=StockMovement.Direction.OUT,
            movement_type__in=_ACTIVE_OUT_TYPES,
        ).values_list("batch__product_id", flat=True)
    )
    followup_ids = set(
        VaccineFollowUp.objects.filter(patient__facility=facility)
        .exclude(
            status__in=[
                VaccineFollowUp.Status.COMPLETED,
                VaccineFollowUp.Status.CANCELLED,
            ]
        )
        .values_list("vaccine_product_id", flat=True)
    )
    incoming_ids = set(
        TransferRequest.objects.filter(
            destination_facility=facility,
            status__in=[
                TransferRequest.Status.APPROVED,
                TransferRequest.Status.DISPATCHED,
                TransferRequest.Status.IN_TRANSIT,
            ],
        ).values_list("product_id", flat=True)
    )
    return batch_ids | usage_ids | followup_ids | incoming_ids


def get_follow_up_demand_in_horizon(facility, product, horizon_days=30, as_of=None):
    """
    Count of open (not COMPLETED/CANCELLED) follow-ups whose due_date falls in
    [today, today + horizon_days] for this product at this facility.
    Lazy import avoids import cycles.
    """
    from vaccinations.models import VaccineFollowUp

    as_of = as_of or timezone.localdate()
    horizon_end = as_of + timedelta(days=horizon_days)

    qs = VaccineFollowUp.objects.filter(
        patient__facility=facility,
        patient__active=True,
        vaccine_product=product,
        due_date__gte=as_of,
        due_date__lte=horizon_end,
    ).exclude(
        status__in=[
            VaccineFollowUp.Status.COMPLETED,
            VaccineFollowUp.Status.CANCELLED,
        ]
    )
    return qs.count()