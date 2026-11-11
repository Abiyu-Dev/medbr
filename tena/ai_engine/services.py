import json
import math
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from coordination.models import SourcingProposal, SupplyGapReport, SupplyRequest
from facilities.models import Facility
from inventory.calculations import (
    get_facility_product_ids,
    get_product_summary,
    get_usable_stock,
)
from inventory.models import Product, StockBatch
from vaccinations.models import VaccineFollowUp

from .client import AIInvalidOutput, AIServiceUnavailable, generate_structured
from .models import AIRecommendation
from .prompts import (
    GAP_PRIORITIZATION_PROMPT,
    INVENTORY_PROMPT,
    SYSTEM_INSTRUCTION,
    TRANSFER_SOURCING_PROMPT,
    VACCINATION_DEMAND_PROMPT,
)
from .schemas import (
    InventoryAnalysisOutput,
    SupplyGapPrioritizationOutput,
    TransferSourcingOutput,
    VaccinationDemandOutput,
)

import json
from django.core.serializers.json import DjangoJSONEncoder

VALID_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


class AIValidationError(Exception):
    """Raised when the caller's scope or parameters are invalid (HTTP 400)."""


# ---------------------------------------------------------------------------
# Snapshot builders (aggregate, no PII)
# ---------------------------------------------------------------------------


def _approved_facilities(facility=None, cap=None):
    qs = Facility.objects.filter(status="APPROVED", is_active=True).order_by("id")
    if facility is not None:
        qs = qs.filter(id=facility.id)
    else:
        qs = qs[: cap or settings.AI_MAX_FACILITIES_PER_CALL]
    return list(qs)


def _product_rows_for(facilities, horizon_days=30):
    rows = []
    for fac in facilities:
        product_ids = get_facility_product_ids(fac, as_of=timezone.localdate())
        products = Product.objects.filter(
            id__in=product_ids, active=True
        ).order_by("id")[: settings.AI_MAX_PRODUCTS_PER_CALL]
        for product in products:
            summary = get_product_summary(
                fac, product, horizon_days=horizon_days
            )
            projected_gap = summary["projected_gap"]
            eligible_surplus = 0
            if (
                projected_gap is not None
                and projected_gap == 0
                and summary["usable_stock"] > (summary["projected_demand"] or 0)
            ):
                eligible_surplus = summary["usable_stock"] - (
                    summary["projected_demand"] or 0
                )
            if (
                summary["usable_stock"] == 0
                and summary["projected_demand"] is None
                and summary["follow_up_demand"] == 0
            ):
                continue  # nothing to say about this row
            rows.append(
                {
                    "facility_id": fac.id,
                    "facility_name": fac.name,
                    "region": fac.region,
                    "has_cold_chain": fac.has_cold_chain,
                    "product_id": product.id,
                    "product_name": product.name,
                    "category": product.category,
                    "requires_cold_chain": product.requires_cold_chain,
                    "unit_of_measure": product.unit_of_measure,
                    "usable_stock": summary["usable_stock"],
                    "reserved_stock": summary["reserved_stock"],
                    "incoming_stock": summary["incoming_stock"],
                    "projected_demand": summary["projected_demand"],
                    "projected_gap": projected_gap,
                    "days_of_stock": summary["days_of_stock"],
                    "follow_up_demand": summary["follow_up_demand"],
                    "near_expiry_quantity": summary["near_expiry_quantity"],
                    "eligible_surplus": eligible_surplus,
                }
            )
    return rows


def _source_eligible_surplus(facility_id, product_id, horizon_days=30):
    """Live re-computation used during validation — never trust the snapshot."""
    try:
        fac = Facility.objects.get(pk=facility_id)
    except Facility.DoesNotExist:
        return None, "unknown_facility"
    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return None, "unknown_product"
    if fac.status != "APPROVED" or not fac.is_active:
        return None, "facility_not_operational"

    summary = get_product_summary(fac, product, horizon_days=horizon_days)
    demand = summary["projected_demand"]
    if demand is None and summary["follow_up_demand"] == 0:
        return None, "unknown_demand"
    gap = summary["projected_gap"]
    if gap is None or gap > 0:
        return None, "source_has_own_shortage"
    surplus = summary["usable_stock"] - (demand or 0)
    if surplus <= 0:
        return None, "no_eligible_surplus"
    return surplus, None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_priority(value):
    return value if value in VALID_PRIORITIES else "MEDIUM"


def _am_text(value, cap=600):
    """Sanitised Amharic translation straight from the model output."""
    return (value or "").strip()[:cap]


def _am_list(values, cap=600, max_items=10):
    return [v.strip()[:cap] for v in (values or []) if v and v.strip()][:max_items]


def _validate_inventory_output(raw, *, horizon_days=30):
    """Return (validated_dict, errors_list)."""
    errors = []

    # --- risks ---
    valid_risks = []
    for item in raw.risks:
        try:
            fac = Facility.objects.get(pk=item.facility_id)
        except Facility.DoesNotExist:
            errors.append(
                {
                    "code": "unknown_facility",
                    "facility_id": item.facility_id,
                    "product_id": item.product_id,
                }
            )
            continue
        if not Product.objects.filter(pk=item.product_id, active=True).exists():
            errors.append(
                {
                    "code": "unknown_product",
                    "facility_id": item.facility_id,
                    "product_id": item.product_id,
                }
            )
            continue
        valid_risks.append(
            {
                "facility_id": fac.id,
                "facility_name": fac.name,
                "product_id": item.product_id,
                "priority": _validate_priority(item.priority),
                "reason": item.reason,
                "reason_amharic": _am_text(item.reason_amharic),
            }
        )

    # --- transfer recommendations ---
    valid_transfers = []
    for item in raw.transfer_recommendations:
        src_id, dst_id, pid = (
            item.source_facility_id,
            item.destination_facility_id,
            item.product_id,
        )
        base = {
            "source_facility_id": src_id,
            "destination_facility_id": dst_id,
            "product_id": pid,
        }

        if src_id == dst_id:
            errors.append({"code": "same_source_and_destination", **base})
            continue
        if item.quantity <= 0:
            errors.append({"code": "non_positive_quantity", **base})
            continue

        surplus, reason = _source_eligible_surplus(src_id, pid, horizon_days)
        if surplus is None:
            errors.append({"code": reason, **base})
            continue
        if item.quantity > surplus:
            errors.append(
                {
                    "code": "quantity_exceeds_source_surplus",
                    "requested": item.quantity,
                    "max": surplus,
                    **base,
                }
            )
            continue

        try:
            dst = Facility.objects.get(pk=dst_id)
        except Facility.DoesNotExist:
            errors.append({"code": "unknown_destination_facility", **base})
            continue
        if dst.status != "APPROVED" or not dst.is_active:
            errors.append({"code": "destination_not_operational", **base})
            continue

        product = Product.objects.get(pk=pid)
        if product.requires_cold_chain and not dst.has_cold_chain:
            errors.append({"code": "destination_lacks_cold_chain", **base})
            continue

        dst_summary = get_product_summary(dst, product, horizon_days=horizon_days)
        dst_gap = dst_summary["projected_gap"]
        if dst_gap is None or dst_gap <= 0:
            errors.append({"code": "destination_has_no_gap", **base})
            continue
        if item.quantity > dst_gap:
            errors.append(
                {
                    "code": "quantity_exceeds_destination_gap",
                    "requested": item.quantity,
                    "max": dst_gap,
                    **base,
                }
            )
            continue

        # Shelf-life check on the best usable batch at the source
        cutoff = timezone.localdate() + timedelta(
            days=settings.AI_MIN_REMAINING_SHELF_LIFE_DAYS
        )
        has_fresh_batch = StockBatch.objects.filter(
            facility_id=src_id,
            product_id=pid,
            storage_status="OK",
            expiry_date__gte=cutoff,
            quantity_available__gt=0,
        ).exists()
        if not has_fresh_batch:
            errors.append({"code": "no_batch_with_sufficient_shelf_life", **base})
            continue

        valid_transfers.append(
            {
                **base,
                "source_facility_name": Facility.objects.get(pk=src_id).name,
                "destination_facility_name": dst.name,
                "product_name": product.name,
                "quantity": item.quantity,
                "reason": item.reason,
                "reason_amharic": _am_text(item.reason_amharic),
            }
        )

    # --- unresolved gaps ---
    valid_gaps = []
    for item in raw.unresolved_gaps:
        if item.quantity <= 0:
            errors.append(
                {
                    "code": "non_positive_gap_quantity",
                    "facility_id": item.facility_id,
                    "product_id": item.product_id,
                }
            )
            continue
        if not Facility.objects.filter(pk=item.facility_id).exists():
            errors.append(
                {
                    "code": "unknown_facility",
                    "facility_id": item.facility_id,
                    "product_id": item.product_id,
                }
            )
            continue
        if not Product.objects.filter(pk=item.product_id).exists():
            errors.append(
                {
                    "code": "unknown_product",
                    "facility_id": item.facility_id,
                    "product_id": item.product_id,
                }
            )
            continue
        valid_gaps.append(
            {
                "facility_id": item.facility_id,
                "product_id": item.product_id,
                "quantity": item.quantity,
            }
        )

    validated = {
        "summary": raw.summary,
        "summary_amharic": _am_text(raw.summary_amharic, cap=2000),
        "risks": valid_risks,
        "transfer_recommendations": valid_transfers,
        "unresolved_gaps": valid_gaps,
        "missing_information": list(raw.missing_information),
        "missing_information_amharic": _am_list(raw.missing_information_amharic),
    }
    return validated, errors


def _validate_gap_prioritization(raw):
    errors = []
    active_ids = set(
        SupplyGapReport.objects.filter(
            status__in=SupplyGapReport.NON_TERMINAL_STATUSES
        ).values_list("id", flat=True)
    )
    seen_ids = set()
    seen_ranks = set()
    valid = []

    for item in raw.ranked_gaps:
        base = {"gap_id": item.gap_id}
        if item.gap_id not in active_ids:
            errors.append({"code": "unknown_or_closed_gap", **base})
            continue
        if item.gap_id in seen_ids:
            errors.append({"code": "duplicate_gap_id", **base})
            continue
        if item.rank < 1 or item.rank > len(raw.ranked_gaps):
            errors.append({"code": "invalid_rank", "rank": item.rank, **base})
            continue
        if item.rank in seen_ranks:
            errors.append({"code": "duplicate_rank", "rank": item.rank, **base})
            continue
        seen_ids.add(item.gap_id)
        seen_ranks.add(item.rank)
        valid.append(
            {
                "gap_id": item.gap_id,
                "priority": _validate_priority(item.priority),
                "rank": item.rank,
                "reason": item.reason,
                "reason_amharic": _am_text(item.reason_amharic),
            }
        )

    valid.sort(key=lambda r: r["rank"])
    return (
        {
            "summary": raw.summary,
            "summary_amharic": _am_text(raw.summary_amharic, cap=2000),
            "ranked_gaps": valid,
            "missing_information": list(raw.missing_information),
            "missing_information_amharic": _am_list(raw.missing_information_amharic),
        },
        errors,
    )


def _validate_vaccination_output(raw, facility):
    errors = []
    allowed_ids = set(
        VaccineFollowUp.objects.filter(patient__facility=facility).values_list(
            "vaccine_product_id", flat=True
        )
    )
    valid = []
    for item in raw.by_product:
        if item.product_id not in allowed_ids:
            errors.append(
                {"code": "product_not_in_scope", "product_id": item.product_id}
            )
            continue
        valid.append(
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "open_follow_ups": item.open_follow_ups,
                "due_next_7_days": item.due_next_7_days,
                "due_next_30_days": item.due_next_30_days,
                "usable_stock": item.usable_stock,
                "projected_gap": item.projected_gap,
                "comment": item.comment,
                "comment_amharic": _am_text(item.comment_amharic),
            }
        )
    return (
        {
            "summary": raw.summary,
            "summary_amharic": _am_text(raw.summary_amharic, cap=2000),
            "by_product": valid,
            "priorities": list(raw.priorities),
            "priorities_amharic": _am_list(raw.priorities_amharic),
            "missing_information": list(raw.missing_information),
            "missing_information_amharic": _am_list(raw.missing_information_amharic),
        },
        errors,
    )


# ---------------------------------------------------------------------------
# Analysis entrypoints
# ---------------------------------------------------------------------------
def _json_safe(obj):
    """
    Round-trip through Django's JSON encoder to guarantee the payload is
    storable in a JSONField. Handles date / datetime / time / Decimal / UUID
    and falls back to str() for anything unexpected.
    """
    return json.loads(json.dumps(obj, cls=DjangoJSONEncoder, default=str))

def _persist(
    *,
    analysis_type,
    requested_by,
    scope_facility,
    model_name,
    summary,
    snapshot,
    raw_output,
    validated_output,
    validation_errors,
    status,
    error="",
):
    return AIRecommendation.objects.create(
        analysis_type=analysis_type,
        status=status,
        scope_facility=scope_facility,
        requested_by=requested_by,
        model_name=model_name,
        summary=summary,
        input_snapshot=_json_safe(snapshot),
        raw_output=raw_output,
        validated_output=validated_output,
        validation_errors=validation_errors,
        error=error,
    )


def _run(payload, *, schema, prompt):
    return generate_structured(
        system_instruction=SYSTEM_INSTRUCTION,
        prompt=prompt.format(**payload),
        schema=schema,
    )


def analyze_inventory(*, user, facility=None, horizon_days=30):
    """
    Run an inventory analysis. Facility users must pass their own facility
    (or leave it blank); central users may pass any facility or none (nationwide).
    """
    facilities = _approved_facilities(
        facility,
        cap=(
            settings.AI_MAX_FACILITIES_PER_CALL
            if facility is None
            else 1
        ),
    )
    if not facilities:
        raise AIValidationError("No approved facilities are available to analyse.")

    rows = _product_rows_for(facilities, horizon_days=horizon_days)
    if not rows:
        raise AIValidationError(
            "No inventory data is available to analyse for the selected scope."
        )

    snapshot = {
        "generated_at": timezone.now().isoformat(),
        "horizon_days": horizon_days,
        "facilities": [
            {
                "facility_id": f.id,
                "facility_name": f.name,
                "region": f.region,
                "has_cold_chain": f.has_cold_chain,
            }
            for f in facilities
        ],
        "rows": rows,
    }

    try:
        raw = _run(
            {"facts": json.dumps(rows, default=str)},
            schema=InventoryAnalysisOutput,
            prompt=INVENTORY_PROMPT,
        )
    except AIServiceUnavailable as exc:
        return _persist(
            analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
            requested_by=user,
            scope_facility=facility,
            model_name=settings.GEMINI_MODEL,
            summary="",
            snapshot=snapshot,
            raw_output={},
            validated_output={},
            validation_errors=[],
            status=AIRecommendation.Status.FAILED,
            error=str(exc),
        )
    except AIInvalidOutput as exc:
        return _persist(
            analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
            requested_by=user,
            scope_facility=facility,
            model_name=settings.GEMINI_MODEL,
            summary="",
            snapshot=snapshot,
            raw_output={},
            validated_output={},
            validation_errors=[],
            status=AIRecommendation.Status.FAILED,
            error=f"Invalid model output: {exc}",
        )

    validated, errors = _validate_inventory_output(raw, horizon_days=horizon_days)
    has_content = bool(
        validated["risks"]
        or validated["transfer_recommendations"]
        or validated["unresolved_gaps"]
    )
    status = (
        AIRecommendation.Status.PENDING_REVIEW
        if has_content or validated["missing_information"]
        else AIRecommendation.Status.INVALID
    )

    return _persist(
        analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
        requested_by=user,
        scope_facility=facility,
        model_name=settings.GEMINI_MODEL,
        summary=validated["summary"],
        snapshot=snapshot,
        raw_output=raw.model_dump(),
        validated_output=validated,
        validation_errors=errors,
        status=status,
    )


def prioritize_supply_gaps(*, user, horizon_days=30):
    gaps = list(
        SupplyGapReport.objects.filter(
            status__in=SupplyGapReport.NON_TERMINAL_STATUSES
        )
        .select_related("facility", "product")
        .order_by("priority", "-uncovered_quantity")[: settings.AI_MAX_PRODUCTS_PER_CALL]
    )
    if not gaps:
        raise AIValidationError("There are no open supply gaps to prioritise.")

    snapshot = {
        "generated_at": timezone.now().isoformat(),
        "horizon_days": horizon_days,
        "gaps": [
            {
                "gap_id": g.id,
                "facility_id": g.facility_id,
                "facility_name": g.facility.name,
                "product_id": g.product_id,
                "product_name": g.product.name,
                "priority": g.priority,
                "uncovered_quantity": g.uncovered_quantity,
                "projected_demand": g.projected_demand,
                "usable_stock": g.usable_stock,
                "reliable_incoming_quantity": g.reliable_incoming_quantity,
                "reporting_horizon_end": g.reporting_horizon_end,
                "status": g.status,
            }
            for g in gaps
        ],
    }

    try:
        raw = _run(
            {"gaps": json.dumps(snapshot["gaps"], default=str)},
            schema=SupplyGapPrioritizationOutput,
            prompt=GAP_PRIORITIZATION_PROMPT,
        )
    except (AIServiceUnavailable, AIInvalidOutput) as exc:
        return _persist(
            analysis_type=AIRecommendation.AnalysisType.SUPPLY_GAP_PRIORITIZATION,
            requested_by=user,
            scope_facility=None,
            model_name=settings.GEMINI_MODEL,
            summary="",
            snapshot=snapshot,
            raw_output={},
            validated_output={},
            validation_errors=[],
            status=AIRecommendation.Status.FAILED,
            error=str(exc),
        )

    validated, errors = _validate_gap_prioritization(raw)
    status = (
        AIRecommendation.Status.PENDING_REVIEW
        if validated["ranked_gaps"]
        else AIRecommendation.Status.INVALID
    )

    return _persist(
        analysis_type=AIRecommendation.AnalysisType.SUPPLY_GAP_PRIORITIZATION,
        requested_by=user,
        scope_facility=None,
        model_name=settings.GEMINI_MODEL,
        summary=validated["summary"],
        snapshot=snapshot,
        raw_output=raw.model_dump(),
        validated_output=validated,
        validation_errors=errors,
        status=status,
    )


def summarize_vaccination_demand(*, user, facility, horizon_days=30):
    today = timezone.localdate()
    in_7 = today + timedelta(days=7)
    in_30 = today + timedelta(days=horizon_days)

    open_statuses = [
        "UPCOMING",
        "DUE",
        "OVERDUE",
        "CONTACT_ATTEMPTED",
        "REVIEW_REQUIRED",
    ]
    base = VaccineFollowUp.objects.filter(
        patient__facility=facility,
        patient__active=True,
        status__in=open_statuses,
    )
    product_ids = set(base.values_list("vaccine_product_id", flat=True))
    if not product_ids:
        raise AIValidationError(
            "No open vaccination follow-ups exist for this facility."
        )

    rows = []
    for pid in product_ids:
        product = Product.objects.get(pk=pid)
        scoped = base.filter(vaccine_product_id=pid)
        summary = get_product_summary(facility, product, horizon_days=horizon_days)
        rows.append(
            {
                "product_id": pid,
                "product_name": product.name,
                "open_follow_ups": scoped.count(),
                "due_next_7_days": scoped.filter(
                    due_date__gte=today, due_date__lte=in_7
                ).count(),
                "due_next_30_days": scoped.filter(
                    due_date__gte=today, due_date__lte=in_30
                ).count(),
                "overdue": scoped.filter(due_date__lt=today).count(),
                "usable_stock": get_usable_stock(facility, product),
                "projected_gap": summary["projected_gap"],
            }
        )

    snapshot = {
        "generated_at": timezone.now().isoformat(),
        "facility_id": facility.id,
        "facility_name": facility.name,
        "horizon_days": horizon_days,
        "rows": rows,
    }

    try:
        raw = _run(
            {"data": json.dumps(rows, default=str)},
            schema=VaccinationDemandOutput,
            prompt=VACCINATION_DEMAND_PROMPT,
        )
    except (AIServiceUnavailable, AIInvalidOutput) as exc:
        return _persist(
            analysis_type=AIRecommendation.AnalysisType.VACCINATION_DEMAND_SUMMARY,
            requested_by=user,
            scope_facility=facility,
            model_name=settings.GEMINI_MODEL,
            summary="",
            snapshot=snapshot,
            raw_output={},
            validated_output={},
            validation_errors=[],
            status=AIRecommendation.Status.FAILED,
            error=str(exc),
        )

    validated, errors = _validate_vaccination_output(raw, facility)
    status = (
        AIRecommendation.Status.PENDING_REVIEW
        if validated["by_product"]
        else AIRecommendation.Status.INVALID
    )

    return _persist(
        analysis_type=AIRecommendation.AnalysisType.VACCINATION_DEMAND_SUMMARY,
        requested_by=user,
        scope_facility=facility,
        model_name=settings.GEMINI_MODEL,
        summary=validated["summary"],
        snapshot=snapshot,
        raw_output=raw.model_dump(),
        validated_output=validated,
        validation_errors=errors,
        status=status,
    )


# ---------------------------------------------------------------------------
# Transfer sourcing (fill open supply requests from facility surplus)
# ---------------------------------------------------------------------------


def _validate_sourcing_output(raw, requests, *, horizon_days=30):
    errors = []
    by_id = {r.id: r for r in requests}
    seen_pairs = set()  # (request_id, source_facility_id)
    alternatives = {}  # request_id -> count, capped so one request can't flood the plan
    valid = []

    for item in raw.proposals:
        base = {
            "request_id": item.request_id,
            "source_facility_id": item.source_facility_id,
            "product_id": item.product_id,
        }
        req = by_id.get(item.request_id)
        if req is None:
            errors.append({"code": "unknown_or_closed_request", **base})
            continue
        pair = (item.request_id, item.source_facility_id)
        if pair in seen_pairs:
            errors.append({"code": "duplicate_source", **base})
            continue
        if alternatives.get(item.request_id, 0) >= 3:
            errors.append({"code": "too_many_alternatives", **base})
            continue
        seen_pairs.add(pair)
        alternatives[item.request_id] = alternatives.get(item.request_id, 0) + 1

        if item.source_facility_id == req.facility_id:
            errors.append({"code": "same_source_and_destination", **base})
            continue
        if item.quantity <= 0:
            errors.append({"code": "non_positive_quantity", **base})
            continue
        if item.product_id != req.product_id:
            errors.append({"code": "product_mismatch", **base})
            continue

        surplus, code = _source_eligible_surplus(
            item.source_facility_id, item.product_id, horizon_days=horizon_days
        )
        if surplus is None:
            errors.append({"code": code, **base})
            continue
        if item.quantity > surplus:
            errors.append(
                {
                    "code": "quantity_exceeds_source_surplus",
                    "requested": item.quantity,
                    "max": surplus,
                    **base,
                }
            )
            continue

        source = Facility.objects.get(pk=item.source_facility_id)
        product = Product.objects.get(pk=req.product_id)
        if product.requires_cold_chain and not source.has_cold_chain:
            errors.append({"code": "source_lacks_cold_chain", **base})
            continue

        cutoff = timezone.localdate() + timedelta(
            days=settings.AI_MIN_REMAINING_SHELF_LIFE_DAYS
        )
        has_fresh_batch = StockBatch.objects.filter(
            facility_id=source.id,
            product_id=req.product_id,
            storage_status="OK",
            expiry_date__gte=cutoff,
            quantity_available__gt=0,
        ).exists()
        if not has_fresh_batch:
            errors.append({"code": "no_batch_with_sufficient_shelf_life", **base})
            continue

        valid.append(
            {
                "request_id": req.id,
                "requesting_facility_id": req.facility_id,
                "requesting_facility_name": req.facility.name,
                "source_facility_id": source.id,
                "source_facility_name": source.name,
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "reason": item.reason,
                "reason_amharic": _am_text(item.reason_amharic),
            }
        )

    return (
        {
            "summary": raw.summary,
            "summary_amharic": _am_text(raw.summary_amharic, cap=2000),
            "proposals": valid,
            "missing_information": list(raw.missing_information),
            "missing_information_amharic": _am_list(raw.missing_information_amharic),
        },
        errors,
    )


def _materialize_sourcing_proposals(recommendation):
    """Persist validated sourcing output as reviewable SourcingProposal rows.

    A re-plan replaces pending proposals for the requests it covers, so the
    review queue always mirrors the latest plan.
    """
    proposals = []
    covered_requests = set()
    for item in (recommendation.validated_output or {}).get("proposals", []):
        try:
            req = SupplyRequest.objects.get(pk=item["request_id"])
        except SupplyRequest.DoesNotExist:
            continue
        if req.status != SupplyRequest.Status.OPEN:
            continue
        covered_requests.add(req.id)
        proposals.append(
            SourcingProposal(
                request=req,
                recommendation=recommendation,
                source_facility_id=item["source_facility_id"],
                product_id=req.product_id,
                quantity=item["quantity"],
                reason=item.get("reason", ""),
                reason_amharic=item.get("reason_amharic", ""),
            )
        )
    if covered_requests:
        SourcingProposal.objects.filter(
            request_id__in=covered_requests,
            status=SourcingProposal.Status.PROPOSED,
        ).exclude(recommendation=recommendation).update(
            status=SourcingProposal.Status.REJECTED,
            review_note="Superseded by a newer AI sourcing plan.",
            reviewed_by=recommendation.requested_by,
            reviewed_at=timezone.now(),
        )
    SourcingProposal.objects.bulk_create(proposals)
    return len(proposals)


def _plan_sourcing_for_requests(*, user, requests, horizon_days=30):
    """Run TRANSFER_SOURCING for the given open supply requests."""
    product_ids = {r.product_id for r in requests}
    facilities = _approved_facilities(cap=settings.AI_MAX_FACILITIES_PER_CALL)
    supply_rows = []
    for fac in facilities:
        for product in Product.objects.filter(
            id__in=product_ids, active=True
        ).order_by("id"):
            summary = get_product_summary(fac, product, horizon_days=horizon_days)
            demand = summary["projected_demand"]
            gap = summary["projected_gap"]
            surplus = 0
            if (
                gap is not None
                and gap <= 0
                and summary["usable_stock"] > (demand or 0)
            ):
                surplus = summary["usable_stock"] - (demand or 0)
            supply_rows.append(
                {
                    "facility_id": fac.id,
                    "facility_name": fac.name,
                    "region": fac.region,
                    "has_cold_chain": fac.has_cold_chain,
                    "product_id": product.id,
                    "product_name": product.name,
                    "requires_cold_chain": product.requires_cold_chain,
                    "usable_stock": summary["usable_stock"],
                    "projected_demand": demand,
                    "projected_gap": gap,
                    "eligible_surplus": surplus,
                }
            )
    # Surplus rows first — the model otherwise anchors on trailing zero rows
    # and reports "no eligible source" even when one exists.
    supply_rows.sort(key=lambda row: (-row["eligible_surplus"], row["facility_id"]))

    request_rows = [
        {
            "request_id": r.id,
            "facility_id": r.facility_id,
            "facility_name": r.facility.name,
            "product_id": r.product_id,
            "product_name": r.product.name,
            "quantity": r.quantity,
            "reason": r.reason,
            "requested_at": r.created_at,
        }
        for r in requests
    ]
    snapshot = {
        "generated_at": timezone.now().isoformat(),
        "horizon_days": horizon_days,
        "requests": request_rows,
        "supply": supply_rows,
    }

    try:
        raw = _run(
            {
                "requests": json.dumps(request_rows, default=str),
                "supply": json.dumps(supply_rows, default=str),
            },
            schema=TransferSourcingOutput,
            prompt=TRANSFER_SOURCING_PROMPT,
        )
    except (AIServiceUnavailable, AIInvalidOutput) as exc:
        return _persist(
            analysis_type=AIRecommendation.AnalysisType.TRANSFER_SOURCING,
            requested_by=user,
            scope_facility=None,
            model_name=settings.GEMINI_MODEL,
            summary="",
            snapshot=snapshot,
            raw_output={},
            validated_output={},
            validation_errors=[],
            status=AIRecommendation.Status.FAILED,
            error=str(exc),
        )

    validated, errors = _validate_sourcing_output(
        raw, requests, horizon_days=horizon_days
    )
    status = (
        AIRecommendation.Status.PENDING_REVIEW
        if validated["proposals"]
        else AIRecommendation.Status.INVALID
    )

    recommendation = _persist(
        analysis_type=AIRecommendation.AnalysisType.TRANSFER_SOURCING,
        requested_by=user,
        scope_facility=None,
        model_name=settings.GEMINI_MODEL,
        summary=validated["summary"],
        snapshot=snapshot,
        raw_output=raw.model_dump(),
        validated_output=validated,
        validation_errors=errors,
        status=status,
    )
    if status == AIRecommendation.Status.PENDING_REVIEW:
        recommendation._materialized_proposals = _materialize_sourcing_proposals(
            recommendation
        )
    return recommendation


def plan_transfer_sourcing(*, user, supply_request_ids=None, horizon_days=30):
    qs = SupplyRequest.objects.filter(
        status=SupplyRequest.Status.OPEN
    ).select_related("facility", "product")
    if supply_request_ids:
        qs = qs.filter(id__in=supply_request_ids)
    requests = list(qs.order_by("id")[: settings.AI_MAX_PRODUCTS_PER_CALL])
    if not requests:
        raise AIValidationError("There are no open supply requests to plan.")
    return _plan_sourcing_for_requests(
        user=user, requests=requests, horizon_days=horizon_days
    )


def plan_gap_sourcing(*, user, gap_ids=None, horizon_days=30):
    """
    Plan donor transfers for open supply gaps: each gap gets (or reuses) an
    open supply request, then the same sourcing pipeline proposes donors.
    """
    from coordination.models import SupplyGapReport, SupplyRequest

    gaps = SupplyGapReport.objects.filter(
        status__in=SupplyGapReport.NON_TERMINAL_STATUSES,
        uncovered_quantity__gt=0,
        facility__status="APPROVED",
        facility__is_active=True,
    ).select_related("facility", "product")
    if gap_ids:
        gaps = gaps.filter(id__in=gap_ids)
    gaps = list(
        gaps.order_by("priority", "-uncovered_quantity")[
            : settings.AI_MAX_PRODUCTS_PER_CALL
        ]
    )
    if not gaps:
        raise AIValidationError(
            "There are no open supply gaps with uncovered stock to plan."
        )

    requests = []
    for gap in gaps:
        request, created = SupplyRequest.objects.get_or_create(
            facility=gap.facility,
            product=gap.product,
            status=SupplyRequest.Status.OPEN,
            defaults={
                "quantity": gap.uncovered_quantity,
                "reason": gap.reason_summary
                or (
                    f"Supply gap ({gap.get_priority_display()}): "
                    f"{gap.uncovered_quantity} units uncovered."
                ),
                "requested_by": user,
                "source_gap": gap,
            },
        )
        if request.source_gap_id is None:
            request.source_gap = gap
            request.save(update_fields=["source_gap", "updated_at"])
        if created and gap.status == SupplyGapReport.Status.OPEN:
            gap.status = SupplyGapReport.Status.ACTION_PLANNED
            gap.save(update_fields=["status", "updated_at"])
        requests.append(request)

    return _plan_sourcing_for_requests(
        user=user, requests=requests, horizon_days=horizon_days
    )


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------


def _create_supply_requests_from_recommendation(recommendation):
    """
    Facility approval of an inventory analysis sends its shortages to the
    central system as supply requests: inbound transfer recommendations,
    unresolved gaps, and risks backed by a live projected gap.
    """
    if recommendation.analysis_type != AIRecommendation.AnalysisType.INVENTORY_ANALYSIS:
        return 0
    facility_id = recommendation.scope_facility_id
    if facility_id is None:
        return 0
    facility = Facility.objects.get(pk=facility_id)
    horizon_days = (recommendation.input_snapshot or {}).get("horizon_days") or 30
    out = recommendation.validated_output or {}

    shortages = {}  # product_id -> (quantity, reason)
    for item in out.get("transfer_recommendations", []):
        if item.get("destination_facility_id") == facility_id:
            shortages[item["product_id"]] = (
                item["quantity"],
                item.get("reason", ""),
            )
    for item in out.get("unresolved_gaps", []):
        if item.get("facility_id") == facility_id and item.get("quantity", 0) > 0:
            shortages.setdefault(
                item["product_id"],
                (item["quantity"], "Uncovered demand from the AI analysis."),
            )
    for item in out.get("risks", []):
        if item.get("facility_id") != facility_id or item["product_id"] in shortages:
            continue
        product = Product.objects.filter(pk=item["product_id"], active=True).first()
        if product is None:
            continue
        gap = get_product_summary(facility, product, horizon_days=horizon_days)[
            "projected_gap"
        ]
        if gap and gap > 0:
            shortages[item["product_id"]] = (gap, item.get("reason", ""))

    created = 0
    for product_id, (quantity, reason) in shortages.items():
        _, made = SupplyRequest.objects.get_or_create(
            facility_id=facility_id,
            product_id=product_id,
            status=SupplyRequest.Status.OPEN,
            defaults={
                "quantity": quantity,
                "reason": reason,
                "source_recommendation": recommendation,
                "requested_by": recommendation.reviewed_by,
            },
        )
        created += int(made)
    return created


@transaction.atomic
def approve_recommendation(*, recommendation, reviewer, note=""):
    locked = AIRecommendation.objects.select_for_update().get(pk=recommendation.pk)
    if not locked.is_reviewable:
        raise AIValidationError(
            f"Cannot approve a recommendation in status {locked.status}."
        )
    locked.status = AIRecommendation.Status.APPROVED
    locked.reviewed_by = reviewer
    locked.reviewed_at = timezone.now()
    locked.review_note = note
    locked.save()
    locked._created_supply_requests = _create_supply_requests_from_recommendation(
        locked
    )
    return locked


@transaction.atomic
def reject_recommendation(*, recommendation, reviewer, note):
    locked = AIRecommendation.objects.select_for_update().get(pk=recommendation.pk)
    if not locked.is_reviewable:
        raise AIValidationError(
            f"Cannot reject a recommendation in status {locked.status}."
        )
    if not note or not note.strip():
        raise AIValidationError("A rejection note is required.")
    locked.status = AIRecommendation.Status.REJECTED
    locked.reviewed_by = reviewer
    locked.reviewed_at = timezone.now()
    locked.review_note = note
    locked.save()
    return locked