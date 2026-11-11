from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from inventory.models import Product, StockBatch
from inventory.services import StockError, administer_vaccination

from .models import Patient, VaccinationRecord, VaccineFollowUp, VaccineSchedule


class VaccinationError(Exception):
    """Raised on any vaccination rule violation. Mapped to HTTP 400 by views."""


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def get_active_schedule(vaccine_product, dose_number):
    return VaccineSchedule.objects.filter(
        vaccine_product=vaccine_product, dose_number=dose_number, active=True
    ).first()


def get_next_dose_schedule(vaccine_product, current_dose_number):
    return get_active_schedule(vaccine_product, current_dose_number + 1)


# ---------------------------------------------------------------------------
# Recording an administered dose
# ---------------------------------------------------------------------------


@transaction.atomic
def record_vaccination(
    *,
    patient,
    vaccine_product,
    dose_number,
    administered_at,
    facility,
    batch,
    recorded_by,
    notes="",
):
    if patient.facility_id != facility.id:
        raise VaccinationError("Patient does not belong to the recording facility.")
    if not facility.provides_vaccination_services:
        raise VaccinationError(
            "This facility is not authorized to provide vaccination services."
        )
    if vaccine_product.category != Product.Category.VACCINE:
        raise VaccinationError("Product must be a VACCINE.")
    if batch.product_id != vaccine_product.id:
        raise VaccinationError("Batch does not match the vaccine product.")
    if batch.facility_id != facility.id:
        raise VaccinationError("Batch does not belong to the recording facility.")
    if dose_number < 1:
        raise VaccinationError("dose_number must be >= 1.")
    if administered_at > timezone.now():
        raise VaccinationError("administered_at cannot be in the future.")

    # Duplicate dose
    if VaccinationRecord.objects.filter(
        patient=patient, vaccine_product=vaccine_product, dose_number=dose_number
    ).exists():
        raise VaccinationError(
            f"Dose {dose_number} already recorded for this patient."
        )

    # Prior dose required
    if dose_number > 1:
        prior = VaccinationRecord.objects.filter(
            patient=patient, vaccine_product=vaccine_product
        ).count()
        if prior < dose_number - 1:
            raise VaccinationError(
                f"Cannot record dose {dose_number} before all previous doses."
            )

    schedule = get_active_schedule(vaccine_product, dose_number)
    if schedule is None:
        raise VaccinationError(
            f"No active schedule exists for {vaccine_product.name} "
            f"dose {dose_number}."
        )

    # Consume stock via vaccination movement (atomic, locks batch)
    try:
        movement, _ = administer_vaccination(
            batch=batch,
            quantity=1,
            performed_by=recorded_by,
            reference_type="VaccinationRecord",
            reference_id=str(patient.id),  # provisional; replaced by record id below
        )
    except StockError as exc:
        raise VaccinationError(str(exc))

    record = VaccinationRecord.objects.create(
        patient=patient,
        vaccine_product=vaccine_product,
        schedule=schedule,
        dose_number=dose_number,
        administered_at=administered_at,
        facility=facility,
        batch=batch,
        recorded_by=recorded_by,
        notes=notes,
    )

    # Update movement's reference_id to point at the record
    movement.reference_id = str(record.id)
    movement.save(update_fields=["reference_id"])

    # Mark any matching open follow-up as COMPLETED
    VaccineFollowUp.objects.filter(
        patient=patient,
        vaccine_product=vaccine_product,
        dose_number=dose_number,
        status__in=VaccineFollowUp.OPEN_STATUSES,
    ).update(status=VaccineFollowUp.Status.COMPLETED)

    # Create follow-up for next dose, if schedule exists
    next_follow_up = _create_next_dose_follow_up(record)
    return record, next_follow_up


def _create_next_dose_follow_up(record):
    next_schedule = get_next_dose_schedule(
        record.vaccine_product, record.dose_number
    )
    if next_schedule is None:
        return None  # series complete

    due_date = _compute_due_date(
        patient=record.patient,
        previous_record=record,
        next_schedule=next_schedule,
    )

    if due_date is None:
        # Cannot compute; create REVIEW_REQUIRED so a human decides
        return VaccineFollowUp.objects.create(
            patient=record.patient,
            vaccine_product=record.vaccine_product,
            dose_number=record.dose_number + 1,
            due_date=timezone.localdate() + timedelta(days=1),
            status=VaccineFollowUp.Status.REVIEW_REQUIRED,
            review_reason=(
                "Due date could not be derived from the active schedule "
                "(no interval and no age rule)."
            ),
        )

    # Only create if there is no existing open follow-up for this dose
    if VaccineFollowUp.objects.filter(
        patient=record.patient,
        vaccine_product=record.vaccine_product,
        dose_number=record.dose_number + 1,
        status__in=VaccineFollowUp.OPEN_STATUSES,
    ).exists():
        return None

    return VaccineFollowUp.objects.create(
        patient=record.patient,
        vaccine_product=record.vaccine_product,
        dose_number=record.dose_number + 1,
        due_date=due_date,
        status=VaccineFollowUp.Status.UPCOMING,
    )


def _compute_due_date(*, patient, previous_record, next_schedule):
    if next_schedule.minimum_interval_days is not None:
        return previous_record.administered_at.date() + timedelta(
            days=next_schedule.minimum_interval_days
        )
    if next_schedule.recommended_age_days is not None:
        return patient.date_of_birth + timedelta(
            days=next_schedule.recommended_age_days
        )
    return None


# ---------------------------------------------------------------------------
# Follow-up status sync (called at list/retrieve time)
# ---------------------------------------------------------------------------


def sync_follow_up_statuses(facility, today=None):
    """
    Move UPCOMING -> DUE/OVERDUE based on today's date.
    Does NOT touch CONTACT_ATTEMPTED / REVIEW_REQUIRED / COMPLETED / CANCELLED.
    Idempotent.
    """
    today = today or timezone.localdate()
    qs = VaccineFollowUp.objects.filter(patient__facility=facility)

    qs.filter(
        status=VaccineFollowUp.Status.UPCOMING, due_date=today
    ).update(status=VaccineFollowUp.Status.DUE)

    qs.filter(
        status=VaccineFollowUp.Status.UPCOMING, due_date__lt=today
    ).update(status=VaccineFollowUp.Status.OVERDUE)

    qs.filter(
        status=VaccineFollowUp.Status.DUE, due_date__lt=today
    ).update(status=VaccineFollowUp.Status.OVERDUE)


# ---------------------------------------------------------------------------
# Contact / review / cancel actions
# ---------------------------------------------------------------------------


@transaction.atomic
def record_contact(
    *, follow_up, outcome, notes="", next_action_date=None, performed_by
):
    if follow_up.status in VaccineFollowUp.TERMINAL_STATUSES:
        raise VaccinationError(
            f"Cannot record contact on a {follow_up.status} follow-up."
        )
    if outcome not in VaccineFollowUp.ContactOutcome.values:
        raise VaccinationError(f"Invalid contact_outcome '{outcome}'.")

    now = timezone.now()
    follow_up.last_contacted_at = now
    follow_up.contact_outcome = outcome
    if notes:
        follow_up.review_reason = (
            (follow_up.review_reason + "\n") if follow_up.review_reason else ""
        ) + f"Contact note: {notes}"

    if outcome == VaccineFollowUp.ContactOutcome.RESCHEDULED:
        if not next_action_date:
            raise VaccinationError(
                "next_action_date is required when outcome is RESCHEDULED."
            )
        follow_up.next_action_date = next_action_date
        follow_up.due_date = next_action_date
        # Reset time-based status so it recomputes
        follow_up.status = VaccineFollowUp.Status.UPCOMING
    elif outcome == VaccineFollowUp.ContactOutcome.REFERRED_FOR_REVIEW:
        follow_up.status = VaccineFollowUp.Status.REVIEW_REQUIRED
    else:
        follow_up.status = VaccineFollowUp.Status.CONTACT_ATTEMPTED

    follow_up.save()
    return follow_up


@transaction.atomic
def mark_review_required(*, follow_up, reason, performed_by):
    if follow_up.status in VaccineFollowUp.TERMINAL_STATUSES:
        raise VaccinationError(
            f"Cannot mark {follow_up.status} follow-up as review required."
        )
    if not reason or not reason.strip():
        raise VaccinationError("reason is required.")
    follow_up.status = VaccineFollowUp.Status.REVIEW_REQUIRED
    follow_up.review_reason = reason
    follow_up.save(update_fields=["status", "review_reason", "updated_at"])
    return follow_up


@transaction.atomic
def cancel_follow_up(*, follow_up, reason, performed_by):
    if follow_up.status in VaccineFollowUp.TERMINAL_STATUSES:
        raise VaccinationError(
            f"Cannot cancel a {follow_up.status} follow-up."
        )
    follow_up.status = VaccineFollowUp.Status.CANCELLED
    if reason:
        follow_up.review_reason = (
            (follow_up.review_reason + "\n") if follow_up.review_reason else ""
        ) + f"Cancelled: {reason}"
    follow_up.save(update_fields=["status", "review_reason", "updated_at"])
    return follow_up


# ---------------------------------------------------------------------------
# Manual follow-up creation
# ---------------------------------------------------------------------------


@transaction.atomic
def create_follow_up(
    *,
    patient,
    vaccine_product,
    dose_number,
    due_date,
    assigned_to=None,
    created_by=None,
):
    if patient.facility_id is None:
        raise VaccinationError("Patient has no facility.")
    if vaccine_product.category != Product.Category.VACCINE:
        raise VaccinationError("Product must be a VACCINE.")
    schedule = get_active_schedule(vaccine_product, dose_number)
    if schedule is None:
        raise VaccinationError(
            f"No active schedule exists for {vaccine_product.name} "
            f"dose {dose_number}."
        )
    if VaccinationRecord.objects.filter(
        patient=patient, vaccine_product=vaccine_product, dose_number=dose_number
    ).exists():
        raise VaccinationError(
            f"Dose {dose_number} already recorded for this patient."
        )
    if VaccineFollowUp.objects.filter(
        patient=patient,
        vaccine_product=vaccine_product,
        dose_number=dose_number,
        status__in=VaccineFollowUp.OPEN_STATUSES,
    ).exists():
        raise VaccinationError("An open follow-up already exists for this dose.")

    return VaccineFollowUp.objects.create(
        patient=patient,
        vaccine_product=vaccine_product,
        dose_number=dose_number,
        due_date=due_date,
        status=VaccineFollowUp.Status.UPCOMING,
        assigned_to=assigned_to,
    )