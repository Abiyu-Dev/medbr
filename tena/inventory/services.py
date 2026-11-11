from datetime import date

from django.db import transaction

from .models import StockBatch, StockMovement


class StockError(Exception):
    """Raised when a stock rule is violated. Mapped to HTTP 400 by the views."""


def _get_idempotent_movement(idempotency_key):
    if not idempotency_key:
        return None
    return StockMovement.objects.filter(idempotency_key=idempotency_key).first()


def _check_batch_usable_for_consumption(batch):
    if batch.storage_status != StockBatch.StorageStatus.OK:
        raise StockError(
            f"Batch is not usable (storage_status={batch.storage_status})."
        )
    if batch.expiry_date < date.today():
        raise StockError("Batch is expired and cannot be consumed or administered.")


@transaction.atomic
def receive_stock(
    *,
    facility,
    product,
    batch_number,
    expiry_date,
    quantity,
    source_reference="",
    performed_by,
    idempotency_key=None,
):
    """
    Atomically create or increment a batch and post a RECEIPT movement.
    Returns (batch, movement, created_boolean).
    """
    if quantity <= 0:
        raise StockError("Quantity must be positive.")
    if product.requires_cold_chain and not facility.has_cold_chain:
        raise StockError(
            "Product requires cold chain but facility is not marked as having cold chain."
        )

    existing_mv = _get_idempotent_movement(idempotency_key)
    if existing_mv:
        return existing_mv.batch, existing_mv, False

    batch = (
        StockBatch.objects.select_for_update()
        .filter(
            facility=facility,
            product=product,
            batch_number=batch_number,
        )
        .first()
    )

    if batch is None:
        batch = StockBatch.objects.create(
            facility=facility,
            product=product,
            batch_number=batch_number,
            expiry_date=expiry_date,
            quantity_received=quantity,
            quantity_available=quantity,
            source_reference=source_reference,
            created_by=performed_by,
        )
    else:
        if batch.expiry_date != expiry_date:
            raise StockError(
                f"Batch '{batch_number}' already exists with expiry "
                f"{batch.expiry_date}; requested expiry is {expiry_date}."
            )
        if batch.storage_status != StockBatch.StorageStatus.OK:
            raise StockError(
                f"Batch is currently {batch.storage_status}; "
                "cannot receive into a non-OK batch."
            )
        batch.quantity_received += quantity
        batch.quantity_available += quantity
        update_fields = ["quantity_received", "quantity_available", "updated_at"]
        if source_reference:
            batch.source_reference = source_reference
            update_fields.append("source_reference")
        batch.save(update_fields=update_fields)

    movement = StockMovement.objects.create(
        batch=batch,
        movement_type=StockMovement.MovementType.RECEIPT,
        direction=StockMovement.Direction.IN,
        quantity=quantity,
        performed_by=performed_by,
        idempotency_key=idempotency_key or None,
    )
    return batch, movement, True


@transaction.atomic
def consume_stock(
    *,
    batch,
    quantity,
    performed_by,
    reason="",
    reference_type="",
    reference_id="",
    idempotency_key=None,
):
    """Reduce stock for consumption. Rejects expired/quarantined batches."""
    if quantity <= 0:
        raise StockError("Quantity must be positive.")

    existing_mv = _get_idempotent_movement(idempotency_key)
    if existing_mv:
        return existing_mv, False

    locked = StockBatch.objects.select_for_update().get(pk=batch.pk)
    _check_batch_usable_for_consumption(locked)
    if locked.quantity_available < quantity:
        raise StockError(
            f"Insufficient stock: available={locked.quantity_available}, requested={quantity}."
        )

    locked.quantity_available -= quantity
    locked.save(update_fields=["quantity_available", "updated_at"])

    movement = StockMovement.objects.create(
        batch=locked,
        movement_type=StockMovement.MovementType.CONSUMPTION,
        direction=StockMovement.Direction.OUT,
        quantity=quantity,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
        idempotency_key=idempotency_key or None,
    )
    return movement, True


@transaction.atomic
def administer_vaccination(
    *,
    batch,
    quantity,
    performed_by,
    reference_type="",
    reference_id="",
    idempotency_key=None,
):
    """
    Reduce stock for a recorded vaccination administration.
    Only `vaccinations.services.record_vaccination` should call this.
    """
    if quantity <= 0:
        raise StockError("Quantity must be positive.")

    existing_mv = _get_idempotent_movement(idempotency_key)
    if existing_mv:
        return existing_mv, False

    locked = StockBatch.objects.select_for_update().get(pk=batch.pk)
    _check_batch_usable_for_consumption(locked)
    if locked.quantity_available < quantity:
        raise StockError(
            f"Insufficient stock: available={locked.quantity_available}, requested={quantity}."
        )

    locked.quantity_available -= quantity
    locked.save(update_fields=["quantity_available", "updated_at"])

    movement = StockMovement.objects.create(
        batch=locked,
        movement_type=StockMovement.MovementType.VACCINATION_ADMINISTRATION,
        direction=StockMovement.Direction.OUT,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
        idempotency_key=idempotency_key or None,
    )
    return movement, True


@transaction.atomic
def record_wastage(
    *,
    batch,
    quantity,
    reason,
    performed_by,
    idempotency_key=None,
):
    """
    Reduce stock via wastage. Expiry/quarantine of the batch is allowed here —
    this is how expired stock gets disposed of.
    """
    if not reason or not reason.strip():
        raise StockError("Wastage reason is required.")
    if quantity <= 0:
        raise StockError("Quantity must be positive.")

    existing_mv = _get_idempotent_movement(idempotency_key)
    if existing_mv:
        return existing_mv, False

    locked = StockBatch.objects.select_for_update().get(pk=batch.pk)
    if locked.quantity_available < quantity:
        raise StockError(
            f"Insufficient stock: available={locked.quantity_available}, requested={quantity}."
        )

    locked.quantity_available -= quantity
    locked.save(update_fields=["quantity_available", "updated_at"])

    movement = StockMovement.objects.create(
        batch=locked,
        movement_type=StockMovement.MovementType.WASTAGE,
        direction=StockMovement.Direction.OUT,
        quantity=quantity,
        reason=reason,
        performed_by=performed_by,
        idempotency_key=idempotency_key or None,
    )
    return movement, True


@transaction.atomic
def adjust_stock(
    *,
    batch,
    quantity,
    direction,
    reason,
    performed_by,
    idempotency_key=None,
):
    """
    Elevated correction. direction is 'IN' or 'OUT'.
    Does NOT bump quantity_received (that counter tracks RECEIPT / TRANSFER_IN only).
    """
    if not reason or not reason.strip():
        raise StockError("Adjustment reason is required.")
    if quantity <= 0:
        raise StockError("Quantity must be positive.")
    if direction not in ("IN", "OUT"):
        raise StockError("Direction must be 'IN' or 'OUT'.")

    existing_mv = _get_idempotent_movement(idempotency_key)
    if existing_mv:
        return existing_mv, False

    locked = StockBatch.objects.select_for_update().get(pk=batch.pk)
    if direction == "OUT":
        if locked.quantity_available < quantity:
            raise StockError(
                f"Insufficient stock: available={locked.quantity_available}, requested={quantity}."
            )
        locked.quantity_available -= quantity
    else:
        locked.quantity_available += quantity
    locked.save(update_fields=["quantity_available", "updated_at"])

    movement = StockMovement.objects.create(
        batch=locked,
        movement_type=StockMovement.MovementType.ADJUSTMENT,
        direction=direction,
        quantity=quantity,
        reason=reason,
        performed_by=performed_by,
        idempotency_key=idempotency_key or None,
    )
    return movement, True