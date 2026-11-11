from django.db import transaction
from django.utils import timezone

from .models import StockBatch, StockMovement, TransferRequest


class TransferError(Exception):
    """Raised when a transfer rule is violated. Mapped to HTTP 400."""


def _fulfill_linked_supply_request(transfer_id):
    from coordination.models import SourcingProposal, SupplyGapReport, SupplyRequest

    proposal = SourcingProposal.objects.filter(
        transfer_id=transfer_id,
        status=SourcingProposal.Status.APPROVED,
    ).select_related("request").first()
    if proposal is None:
        return
    request = SupplyRequest.objects.filter(
        pk=proposal.request_id,
        status=SupplyRequest.Status.PLANNED,
    ).first()
    if request is None:
        return
    request.status = SupplyRequest.Status.FULFILLED
    request.save(update_fields=["status", "updated_at"])
    gap = request.source_gap
    if gap is not None and gap.status not in SupplyGapReport.TERMINAL_STATUSES:
        gap.status = SupplyGapReport.Status.RESOLVED
        gap.resolution_notes = (
            f"Covered by transfer #{transfer_id} from "
            f"{proposal.source_facility.name}."
        )
        gap.save(update_fields=["status", "resolution_notes", "resolved_at", "updated_at"])


def _reopen_linked_supply_request(transfer_id):
    from coordination.models import SourcingProposal, SupplyGapReport, SupplyRequest

    proposal = SourcingProposal.objects.filter(
        transfer_id=transfer_id,
        status=SourcingProposal.Status.APPROVED,
    ).first()
    if proposal is None:
        return
    proposal.status = SourcingProposal.Status.PROPOSED
    proposal.transfer = None
    proposal.review_note = "Linked transfer was cancelled; awaiting re-review."
    proposal.reviewed_at = None
    proposal.reviewed_by = None
    proposal.save(update_fields=["status", "transfer", "review_note", "reviewed_at", "reviewed_by", "updated_at"])
    request = SupplyRequest.objects.filter(
        pk=proposal.request_id,
        status=SupplyRequest.Status.PLANNED,
    ).first()
    if request is None:
        return
    request.status = SupplyRequest.Status.OPEN
    request.save(update_fields=["status", "updated_at"])
    gap = request.source_gap
    if gap is not None and gap.status not in SupplyGapReport.TERMINAL_STATUSES:
        gap.status = SupplyGapReport.Status.OPEN
        gap.save(update_fields=["status", "resolved_at", "updated_at"])


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


@transaction.atomic
def create_transfer_request(
    *,
    source_facility,
    destination_facility,
    product,
    source_batch,
    quantity_requested,
    priority,
    requested_by,
    expected_dispatch_at=None,
    expected_arrival_at=None,
    notes="",
):
    if source_facility.id == destination_facility.id:
        raise TransferError("Source and destination facilities must differ.")
    for fac in (source_facility, destination_facility):
        if fac.status != "APPROVED" or not fac.is_active:
            raise TransferError(
                f"Facility '{fac.name}' is not approved and active."
            )

    batch = StockBatch.objects.select_for_update().get(pk=source_batch.pk)
    if batch.facility_id != source_facility.id:
        raise TransferError("Source batch does not belong to the source facility.")
    if batch.product_id != product.id:
        raise TransferError("Product does not match the source batch's product.")
    if not batch.is_usable():
        raise TransferError(
            f"Source batch is not usable (status={batch.storage_status}, "
            f"expiry={batch.expiry_date})."
        )
    if quantity_requested <= 0:
        raise TransferError("quantity_requested must be positive.")

    free = batch.quantity_available - batch.quantity_reserved
    if quantity_requested > free:
        raise TransferError(
            f"Insufficient unreserved stock: only {free} free units in source batch."
        )

    return TransferRequest.objects.create(
        source_facility=source_facility,
        destination_facility=destination_facility,
        product=product,
        source_batch=batch,
        quantity_requested=quantity_requested,
        priority=priority,
        requested_by=requested_by,
        expected_dispatch_at=expected_dispatch_at,
        expected_arrival_at=expected_arrival_at,
        notes=notes,
        status=TransferRequest.Status.REQUESTED,
    )


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@transaction.atomic
def approve_transfer(*, transfer, approved_by, quantity_approved):
    locked = TransferRequest.objects.select_for_update().get(pk=transfer.pk)
    if locked.status not in (
        TransferRequest.Status.REQUESTED,
        TransferRequest.Status.UNDER_REVIEW,
    ):
        raise TransferError(f"Cannot approve a transfer in status {locked.status}.")
    if quantity_approved <= 0:
        raise TransferError("quantity_approved must be positive.")
    if quantity_approved > locked.quantity_requested:
        raise TransferError("quantity_approved cannot exceed quantity_requested.")

    batch = StockBatch.objects.select_for_update().get(pk=locked.source_batch_id)
    if not batch.is_usable():
        raise TransferError("Source batch is no longer usable.")
    free = batch.quantity_available - batch.quantity_reserved
    if quantity_approved > free:
        raise TransferError(
            f"Insufficient free stock in source batch: {free} available, "
            f"{quantity_approved} requested."
        )

    batch.quantity_reserved += quantity_approved
    batch.save(update_fields=["quantity_reserved", "updated_at"])

    locked.quantity_approved = quantity_approved
    locked.status = TransferRequest.Status.APPROVED
    locked.approved_by = approved_by
    locked.approved_at = timezone.now()
    locked.save()
    return locked


@transaction.atomic
def reject_transfer(*, transfer, reviewed_by, rejection_reason):
    if not rejection_reason or not rejection_reason.strip():
        raise TransferError("Rejection reason is required.")
    locked = TransferRequest.objects.select_for_update().get(pk=transfer.pk)
    if locked.status not in (
        TransferRequest.Status.REQUESTED,
        TransferRequest.Status.UNDER_REVIEW,
    ):
        raise TransferError(f"Cannot reject a transfer in status {locked.status}.")

    locked.status = TransferRequest.Status.REJECTED
    locked.rejection_reason = rejection_reason
    locked.approved_by = reviewed_by  # reviewer field doubles for rejections
    locked.approved_at = timezone.now()
    locked.save()
    return locked


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@transaction.atomic
def dispatch_transfer(*, transfer, performed_by, notes=""):
    locked = TransferRequest.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != TransferRequest.Status.APPROVED:
        raise TransferError(
            f"Cannot dispatch a transfer in status {locked.status}."
        )

    batch = StockBatch.objects.select_for_update().get(pk=locked.source_batch_id)
    if batch.quantity_available < locked.quantity_approved:
        raise TransferError(
            f"Source batch only has {batch.quantity_available} units; "
            f"{locked.quantity_approved} are committed."
        )

    batch.quantity_available -= locked.quantity_approved
    batch.quantity_reserved = max(
        0, batch.quantity_reserved - locked.quantity_approved
    )
    batch.save(update_fields=["quantity_available", "quantity_reserved", "updated_at"])

    StockMovement.objects.create(
        batch=batch,
        movement_type=StockMovement.MovementType.TRANSFER_OUT,
        direction=StockMovement.Direction.OUT,
        quantity=locked.quantity_approved,
        reference_type="TransferRequest",
        reference_id=str(locked.id),
        reason=notes or "Dispatched transfer",
        performed_by=performed_by,
        idempotency_key=f"transfer-{locked.id}-out",
    )

    locked.status = TransferRequest.Status.DISPATCHED
    locked.save()
    return locked


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------


@transaction.atomic
def receive_transfer(*, transfer, performed_by, quantity_received, condition, notes=""):
    locked = TransferRequest.objects.select_for_update().get(pk=transfer.pk)
    if locked.status not in (
        TransferRequest.Status.DISPATCHED,
        TransferRequest.Status.IN_TRANSIT,
    ):
        raise TransferError(
            f"Cannot receive a transfer in status {locked.status}."
        )
    if quantity_received <= 0:
        raise TransferError("quantity_received must be positive.")
    if quantity_received > locked.quantity_approved:
        raise TransferError(
            f"quantity_received ({quantity_received}) exceeds quantity_approved "
            f"({locked.quantity_approved})."
        )

    condition = (condition or "OK").upper()
    allowed_conditions = {"OK", "DAMAGED", "TEMPERATURE_EXCURSION"}
    if condition not in allowed_conditions:
        raise TransferError(f"Invalid condition '{condition}'.")

    # Destination batch: preserve source batch_number and expiry for traceability
    existing = (
        StockBatch.objects.select_for_update()
        .filter(
            facility=locked.destination_facility,
            product=locked.product,
            batch_number=locked.source_batch.batch_number,
        )
        .first()
    )

    if existing is not None:
        if existing.expiry_date != locked.source_batch.expiry_date:
            raise TransferError(
                f"Destination already holds batch '{existing.batch_number}' with "
                f"expiry {existing.expiry_date}; source batch expiry is "
                f"{locked.source_batch.expiry_date}. Cannot merge mismatched batches."
            )
        if existing.storage_status != StockBatch.StorageStatus.OK and condition == "OK":
            raise TransferError(
                f"Destination batch is currently {existing.storage_status}; "
                "cannot receive into a non-OK batch with condition OK."
            )
        existing.quantity_available += quantity_received
        existing.quantity_received += quantity_received
        if condition != "OK":
            existing.storage_status = condition
        existing.save(
            update_fields=[
                "quantity_available",
                "quantity_received",
                "storage_status",
                "updated_at",
            ]
        )
        dest_batch = existing
    else:
        dest_batch = StockBatch.objects.create(
            facility=locked.destination_facility,
            product=locked.product,
            batch_number=locked.source_batch.batch_number,
            expiry_date=locked.source_batch.expiry_date,
            quantity_received=quantity_received,
            quantity_available=quantity_received,
            storage_status=condition if condition != "OK" else "OK",
            source_reference=f"Transfer #{locked.id}",
            created_by=performed_by,
        )

    StockMovement.objects.create(
        batch=dest_batch,
        movement_type=StockMovement.MovementType.TRANSFER_IN,
        direction=StockMovement.Direction.IN,
        quantity=quantity_received,
        reference_type="TransferRequest",
        reference_id=str(locked.id),
        reason=notes or "Received transfer",
        performed_by=performed_by,
        idempotency_key=f"transfer-{locked.id}-in",
    )

    locked.quantity_received = quantity_received
    locked.received_by = performed_by
    locked.received_at = timezone.now()
    locked.condition_on_receipt = condition
    locked.status = TransferRequest.Status.RECEIVED
    locked.save()

    _fulfill_linked_supply_request(locked.id)

    return locked, dest_batch


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@transaction.atomic
def cancel_transfer(*, transfer, performed_by, reason=""):
    locked = TransferRequest.objects.select_for_update().get(pk=transfer.pk)
    if locked.status not in (
        TransferRequest.Status.REQUESTED,
        TransferRequest.Status.UNDER_REVIEW,
        TransferRequest.Status.APPROVED,
    ):
        raise TransferError(f"Cannot cancel a transfer in status {locked.status}.")

    if locked.status == TransferRequest.Status.APPROVED:
        batch = StockBatch.objects.select_for_update().get(pk=locked.source_batch_id)
        batch.quantity_reserved = max(
            0, batch.quantity_reserved - locked.quantity_approved
        )
        batch.save(update_fields=["quantity_reserved", "updated_at"])

    locked.status = TransferRequest.Status.CANCELLED
    if reason:
        locked.notes = (locked.notes + "\n" if locked.notes else "") + f"Cancelled: {reason}"
    locked.save()

    _reopen_linked_supply_request(locked.id)
    return locked