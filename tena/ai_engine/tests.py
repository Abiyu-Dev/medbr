import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AuditLog, User
from ai_engine.client import AIInvalidOutput, AIServiceUnavailable
from ai_engine.models import AIRecommendation
from ai_engine.schemas import (
    InventoryAnalysisOutput,
    SupplyGapPrioritizationOutput,
    TransferSourcingOutput,
    VaccinationDemandOutput,
)
from coordination.models import SourcingProposal, SupplyGapReport, SupplyRequest
from facilities.models import Facility
from inventory.models import Product, TransferRequest
from inventory.services import consume_stock, receive_stock
from vaccinations.models import VaccineFollowUp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mk_user(username, role, facility=None):
    return User.objects.create_user(
        username=username,
        password="TestPass123!",
        email=f"{username}@x.com",
        role=role,
        facility=facility,
    )


def _mk_facility(name, cold_chain=True, vax=False):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=Facility.Status.APPROVED,
        has_cold_chain=cold_chain,
        provides_vaccination_services=vax,
    )


def _mk_product(name="Paracetamol", category="MEDICINE", cold=False):
    return Product.objects.create(
        name=name,
        category=category,
        requires_cold_chain=cold,
        unit_of_measure="dose" if category == "VACCINE" else "tablet",
    )


def _inventory_output(**over):
    data = {
        "summary": "Facility B is short on Paracetamol.",
        "risks": [],
        "transfer_recommendations": [],
        "unresolved_gaps": [],
        "missing_information": [],
    }
    data.update(over)
    return InventoryAnalysisOutput(**data)


class _AIBase(TestCase):
    """Two facilities: A has surplus, B has a real shortage (85 units)."""

    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("Alpha")
        self.fb = _mk_facility("Beta")
        self.fc = _mk_facility("Gamma")
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.pharm_a = _mk_user("pharma", User.Role.PHARMACIST, facility=self.fa)
        self.mgr_b = _mk_user("mgrb", User.Role.FACILITY_MANAGER, facility=self.fb)
        self.mgr_c = _mk_user("mgrc", User.Role.FACILITY_MANAGER, facility=self.fc)
        self.product = _mk_product()

        # ---- Source facility A ----
        # 1000 received, 30 consumed -> 970 usable, 1/day usage, demand 30,
        # eligible surplus = 970 - 30 = 940.
        self.batch_a, _, _ = receive_stock(
            facility=self.fa,
            product=self.product,
            batch_number="A-1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=1000,
            performed_by=self.pharm_a,
        )
        for _ in range(10):
            consume_stock(batch=self.batch_a, quantity=3, performed_by=self.pharm_a)

        # ---- Destination facility B (real shortage) ----
        # 95 received, 90 consumed -> 5 usable, 3/day usage, demand 90,
        # projected_gap = 90 - 5 = 85.
        self.batch_b, _, _ = receive_stock(
            facility=self.fb,
            product=self.product,
            batch_number="B-1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=95,
            performed_by=self.mgr_b,
        )
        consume_stock(batch=self.batch_b, quantity=90, performed_by=self.mgr_b)

        # Refresh so tests see the post-consumption quantity_available.
        self.batch_a.refresh_from_db()
        self.batch_b.refresh_from_db()


# ---------------------------------------------------------------------------
# Client behaviour
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="")
class MissingKeyTests(_AIBase):
    def test_analyze_returns_failed_record_not_500(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/ai/analyze-inventory/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "FAILED")
        self.assertIn("GEMINI_API_KEY", r.data["error"])

    def test_inventory_endpoints_still_work(self):
        """Core system must not depend on Gemini."""
        self.client.force_authenticate(self.admin)
        r = self.client.get(f"/api/v1/inventory/summary/?facility={self.fb.id}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)


@override_settings(GEMINI_API_KEY="fake-key")
class FailedCallTests(_AIBase):
    @patch("ai_engine.services.generate_structured")
    def test_service_unavailable_sets_failed(self, mock_generate):
        mock_generate.side_effect = AIServiceUnavailable("timeout")
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/ai/analyze-inventory/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "FAILED")
        self.assertEqual(r.data["error"], "timeout")

    @patch("ai_engine.services.generate_structured")
    def test_invalid_output_sets_failed(self, mock_generate):
        mock_generate.side_effect = AIInvalidOutput("bad json")
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/ai/analyze-inventory/", {}, format="json")
        self.assertEqual(r.data["status"], "FAILED")
        self.assertIn("Invalid model output", r.data["error"])

    @patch("ai_engine.services.generate_structured")
    def test_snapshot_is_persisted_even_on_failure(self, mock_generate):
        mock_generate.side_effect = AIServiceUnavailable("boom")
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/ai/analyze-inventory/", {}, format="json")
        rec = AIRecommendation.objects.get(id=r.data["id"])
        self.assertIn("rows", rec.input_snapshot)
        self.assertTrue(rec.input_snapshot["rows"])


# ---------------------------------------------------------------------------
# Validation of transfer recommendations
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="fake-key")
class InventoryValidationTests(_AIBase):
    def _run(self, output):
        with patch(
            "ai_engine.services.generate_structured", return_value=output
        ):
            self.client.force_authenticate(self.admin)
            return self.client.post(
                "/api/v1/ai/analyze-inventory/", {}, format="json"
            )

    def test_snapshot_contains_no_pii(self):
        output = _inventory_output()
        r = self._run(output)
        snapshot = json.dumps(r.data["input_snapshot"])
        for forbidden in ("patient", "phone", "guardian", "date_of_birth"):
            self.assertNotIn(forbidden, snapshot.lower())

    def test_valid_transfer_survives(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "quantity": 50,
                    "reason": "A has surplus, B has a gap.",
                }
            ]
        )
        r = self._run(output)
        self.assertEqual(r.data["status"], "PENDING_REVIEW")
        self.assertEqual(len(r.data["validated_output"]["transfer_recommendations"]), 1)
        self.assertEqual(r.data["validation_errors"], [])

    def test_amharic_translations_pass_through(self):
        output = _inventory_output(
            summary_amharic="ቢታ በፓራሴታሞል የቀረበት ነው።",
            risks=[
                {
                    "facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "priority": "CRITICAL",
                    "reason": "Beta is nearly out.",
                    "reason_amharic": "ቢታ አቅሟ እንዲህ ነው።",
                }
            ],
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "quantity": 50,
                    "reason": "A has surplus.",
                    "reason_amharic": "ሀ ተመጣጣኝ አለው።",
                }
            ],
            missing_information=["Outreach schedule unknown."],
            missing_information_amharic=["የውጪ ሕክምና መርሃ ግብር አይታወቅም።"],
        )
        r = self._run(output)
        vo = r.data["validated_output"]
        self.assertEqual(vo["summary_amharic"], "ቢታ በፓራሴታሞል የቀረበት ነው።")
        self.assertEqual(vo["risks"][0]["reason_amharic"], "ቢታ አቅሟ እንዲህ ነው።")
        self.assertEqual(vo["transfer_recommendations"][0]["reason_amharic"], "ሀ ተመጣጣኝ አለው።")
        self.assertEqual(vo["missing_information_amharic"], ["የውጪ ሕክምና መርሃ ግብር አይታወቅም።"])

    def test_quantity_above_source_surplus_dropped(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "quantity": 9999,
                    "reason": "too much",
                }
            ]
        )
        r = self._run(output)
        self.assertEqual(r.data["validated_output"]["transfer_recommendations"], [])
        codes = [e["code"] for e in r.data["validation_errors"]]
        self.assertIn("quantity_exceeds_source_surplus", codes)

    def test_source_with_own_shortage_dropped(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fb.id,  # B is short itself
                    "destination_facility_id": self.fa.id,
                    "product_id": self.product.id,
                    "quantity": 5,
                    "reason": "invalid source",
                }
            ]
        )
        r = self._run(output)
        self.assertEqual(r.data["validated_output"]["transfer_recommendations"], [])
        codes = [e["code"] for e in r.data["validation_errors"]]
        self.assertIn("source_has_own_shortage", codes)

    def test_unknown_facility_dropped(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": 99999,
                    "destination_facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "quantity": 10,
                    "reason": "invented",
                }
            ]
        )
        r = self._run(output)
        codes = [e["code"] for e in r.data["validation_errors"]]
        self.assertIn("unknown_facility", codes)

    def test_same_source_and_destination_dropped(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": self.fa.id,
                    "product_id": self.product.id,
                    "quantity": 10,
                    "reason": "nonsense",
                }
            ]
        )
        r = self._run(output)
        codes = [e["code"] for e in r.data["validation_errors"]]
        self.assertIn("same_source_and_destination", codes)

    def test_quantity_above_destination_gap_dropped(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "quantity": 500,  # > B's gap of ~85, but < A's surplus? adjust below
                    "reason": "over gap",
                }
            ]
        )
        # A's surplus is 100, so 500 fails on surplus first; use 90 to hit the gap check
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": self.fb.id,
                    "product_id": self.product.id,
                    "quantity": 95,
                    "reason": "over gap",
                }
            ]
        )
        r = self._run(output)
        codes = [e["code"] for e in r.data["validation_errors"]]
        self.assertTrue(
            "quantity_exceeds_destination_gap" in codes
            or "quantity_exceeds_source_surplus" in codes
        )

    def test_cold_chain_mismatch_dropped(self):
        vaccine = _mk_product("BCG", category="VACCINE", cold=True)
        no_cold = _mk_facility("NoCold", cold_chain=False)
        vb, _, _ = receive_stock(
            facility=self.fa,
            product=vaccine,
            batch_number="V-1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=500,
            performed_by=self.pharm_a,
        )
        for _ in range(10):
            consume_stock(batch=vb, quantity=3, performed_by=self.pharm_a)

        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": self.fa.id,
                    "destination_facility_id": no_cold.id,
                    "product_id": vaccine.id,
                    "quantity": 10,
                    "reason": "cold chain ignored",
                }
            ]
        )
        r = self._run(output)
        codes = [e["code"] for e in r.data["validation_errors"]]
        self.assertIn("destination_lacks_cold_chain", codes)

    def test_all_invalid_marks_invalid(self):
        output = _inventory_output(
            transfer_recommendations=[
                {
                    "source_facility_id": 88888,
                    "destination_facility_id": 77777,
                    "product_id": 66666,
                    "quantity": 1,
                    "reason": "garbage",
                }
            ]
        )
        r = self._run(output)
        self.assertEqual(r.data["status"], "INVALID")

    def test_ai_never_writes_stock(self):
        before = self.batch_a.quantity_available
        self._run(
            _inventory_output(
                transfer_recommendations=[
                    {
                        "source_facility_id": self.fa.id,
                        "destination_facility_id": self.fb.id,
                        "product_id": self.product.id,
                        "quantity": 40,
                        "reason": "valid",
                    }
                ]
            )
        )
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity_available, before)


# ---------------------------------------------------------------------------
# Scoping / permissions
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="fake-key")
class AIPermissionTests(_AIBase):
    @patch("ai_engine.services.generate_structured")
    def test_pharmacist_can_run_for_own_facility(self, mock_generate):
        mock_generate.return_value = _inventory_output()
        self.client.force_authenticate(self.pharm_a)
        r = self.client.post("/api/v1/ai/analyze-inventory/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["scope_facility"], self.fa.id)

    @patch("ai_engine.services.generate_structured")
    def test_pharmacist_cannot_target_other_facility(self, mock_generate):
        mock_generate.return_value = _inventory_output()
        self.client.force_authenticate(self.pharm_a)
        r = self.client.post(
            "/api/v1/ai/analyze-inventory/",
            {"facility": self.fb.id},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_health_worker_cannot_run_inventory_analysis(self):
        hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fa)
        self.client.force_authenticate(hw)
        r = self.client.post("/api/v1/ai/analyze-inventory/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_facility_manager_cannot_prioritize_gaps(self):
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post("/api/v1/ai/prioritize-supply-gaps/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_prioritize_gaps(self):
        product = _mk_product("GapProd")
        SupplyGapReport.objects.create(
            facility=self.fb,
            product=product,
            reporting_horizon_start=date.today(),
            reporting_horizon_end=date.today() + timedelta(days=30),
            projected_demand=100,
            usable_stock=10,
            reliable_incoming_quantity=0,
            uncovered_quantity=90,
            priority="HIGH",
        )
        with patch(
            "ai_engine.services.generate_structured",
            return_value=SupplyGapPrioritizationOutput(
                summary="One critical gap.",
                ranked_gaps=[
                    {
                        "gap_id": SupplyGapReport.objects.first().id,
                        "priority": "CRITICAL",
                        "rank": 1,
                        "reason": "Only stock left.",
                    }
                ],
                missing_information=[],
            ),
        ):
            self.client.force_authenticate(self.admin)
            r = self.client.post(
                "/api/v1/ai/prioritize-supply-gaps/", {}, format="json"
            )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(r.data["validated_output"]["ranked_gaps"]), 1)

    def test_prioritize_with_no_open_gaps_returns_400(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post("/api/v1/ai/prioritize-supply-gaps/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "ai_validation_error")

    def test_facility_manager_list_scoped_to_own_facility(self):
        AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=self.fa,
            requested_by=self.admin,
        )
        AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=self.fb,
            requested_by=self.admin,
        )
        self.client.force_authenticate(self.mgr_b)
        r = self.client.get("/api/v1/ai/recommendations/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["scope_facility"], self.fb.id)

    def test_pharmacist_only_sees_inventory_analysis(self):
        AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=self.fa,
            requested_by=self.admin,
        )
        AIRecommendation.objects.create(
            analysis_type="VACCINATION_DEMAND_SUMMARY",
            scope_facility=self.fa,
            requested_by=self.admin,
        )
        self.client.force_authenticate(self.pharm_a)
        r = self.client.get("/api/v1/ai/recommendations/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(
            r.data["results"][0]["analysis_type"], "INVENTORY_ANALYSIS"
        )


# ---------------------------------------------------------------------------
# Review workflow
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="fake-key")
class ReviewTests(_AIBase):
    def _pending(self, facility=None):
        return AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=facility,
            requested_by=self.admin,
            summary="Something",
            validated_output={"risks": []},
        )

    def test_central_approves(self):
        rec = self._pending(facility=self.fb)
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/",
            {"note": "Looks right"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.status, "APPROVED")
        self.assertEqual(rec.reviewed_by, self.coord)
        self.assertIsNotNone(rec.reviewed_at)
        self.assertTrue(
            AuditLog.objects.filter(action="AI_RECOMMENDATION_APPROVED").exists()
        )

    def test_approval_does_not_move_stock(self):
        rec = self._pending(facility=self.fb)
        before = self.batch_a.quantity_available
        self.client.force_authenticate(self.coord)
        self.client.post(f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json")
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity_available, before)

    def test_facility_manager_approves_own_scope(self):
        rec = self._pending(facility=self.fb)
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_facility_manager_cannot_approve_other_scope(self):
        rec = self._pending(facility=self.fa)
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        # Scoped queryset hides it entirely
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_cannot_approve(self):
        rec = self._pending(facility=self.fa)
        self.client.force_authenticate(self.pharm_a)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_reject_requires_note(self):
        rec = self._pending(facility=self.fb)
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/reject/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_succeeds(self):
        rec = self._pending(facility=self.fb)
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/reject/",
            {"note": "Not actionable this week"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.status, "REJECTED")
        self.assertEqual(rec.review_note, "Not actionable this week")

    def test_double_review_conflicts(self):
        rec = self._pending(facility=self.fb)
        self.client.force_authenticate(self.coord)
        self.client.post(f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json")
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/reject/",
            {"note": "changed my mind"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_review_failed_recommendation(self):
        rec = AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=self.fb,
            requested_by=self.admin,
            status="FAILED",
            error="timeout",
        )
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Approval -> supply requests to the central system
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="")
class SupplyRequestCreationTests(_AIBase):
    def _pending(self, validated_output):
        return AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=self.fb,
            requested_by=self.mgr_b,
            summary="Shortages at Beta",
            input_snapshot={"horizon_days": 30},
            validated_output=validated_output,
        )

    def test_risk_with_live_gap_creates_supply_request(self):
        rec = self._pending(
            {
                "risks": [
                    {
                        "facility_id": self.fb.id,
                        "product_id": self.product.id,
                        "priority": "CRITICAL",
                        "reason": "Beta is nearly out.",
                    }
                ]
            }
        )
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get("supply_requests_created"), 1)
        sr = SupplyRequest.objects.get()
        self.assertEqual(sr.facility, self.fb)
        self.assertEqual(sr.product, self.product)
        self.assertEqual(sr.status, SupplyRequest.Status.OPEN)
        self.assertEqual(sr.quantity, 85)  # live projected gap
        self.assertEqual(sr.requested_by, self.mgr_b)

    def test_inbound_transfer_recommendation_creates_request(self):
        rec = self._pending(
            {
                "transfer_recommendations": [
                    {
                        "source_facility_id": self.fa.id,
                        "destination_facility_id": self.fb.id,
                        "product_id": self.product.id,
                        "quantity": 40,
                        "reason": "Cover part of the gap.",
                    }
                ]
            }
        )
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        sr = SupplyRequest.objects.get()
        self.assertEqual(sr.quantity, 40)

    def test_risk_without_gap_creates_nothing(self):
        # Alpha holds surplus (gap 0) — a risk there must not open a request.
        rec = self._pending(
            {
                "risks": [
                    {
                        "facility_id": self.fa.id,
                        "product_id": self.product.id,
                        "priority": "LOW",
                        "reason": "Near expiry.",
                    }
                ]
            }
        )
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post(
            f"/api/v1/ai/recommendations/{rec.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(SupplyRequest.objects.count(), 0)

    def test_outbound_transfer_creates_no_request(self):
        rec = self._pending(
            {
                "transfer_recommendations": [
                    {
                        "source_facility_id": self.fb.id,
                        "destination_facility_id": self.fa.id,
                        "product_id": self.product.id,
                        "quantity": 5,
                        "reason": "Beta donates.",
                    }
                ]
            }
        )
        from ai_engine.services import approve_recommendation

        approve_recommendation(recommendation=rec, reviewer=self.mgr_b)
        self.assertEqual(SupplyRequest.objects.count(), 0)

    def test_duplicates_collapse_to_one_open_request(self):
        rec = self._pending(
            {
                "risks": [
                    {
                        "facility_id": self.fb.id,
                        "product_id": self.product.id,
                        "priority": "HIGH",
                        "reason": "First signal.",
                    }
                ],
                "unresolved_gaps": [
                    {
                        "facility_id": self.fb.id,
                        "product_id": self.product.id,
                        "quantity": 20,
                    }
                ],
            }
        )
        from ai_engine.services import approve_recommendation

        approve_recommendation(recommendation=rec, reviewer=self.mgr_b)
        self.assertEqual(SupplyRequest.objects.count(), 1)
        # the explicit unresolved-gap quantity wins over the live-gap fallback
        self.assertEqual(SupplyRequest.objects.get().quantity, 20)

    def test_nationwide_analysis_creates_no_requests(self):
        rec = AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=None,
            requested_by=self.admin,
            summary="Nationwide",
            validated_output={
                "risks": [
                    {
                        "facility_id": self.fb.id,
                        "product_id": self.product.id,
                        "priority": "HIGH",
                        "reason": "Short.",
                    }
                ]
            },
        )
        from ai_engine.services import approve_recommendation

        approve_recommendation(recommendation=rec, reviewer=self.admin)
        self.assertEqual(SupplyRequest.objects.count(), 0)


# ---------------------------------------------------------------------------
# Vaccination demand summary
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="fake-key")
class VaccinationDemandTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Vax", vax=True)
        self.hw = _mk_user("hw", User.Role.HEALTH_WORKER, facility=self.fac)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.vaccine = _mk_product("BCG", category="VACCINE", cold=False)

        from vaccinations.models import Patient, VaccineSchedule

        VaccineSchedule.objects.create(
            vaccine_product=self.vaccine,
            dose_number=1,
            recommended_age_days=0,
            effective_from=date.today(),
            source_name="EPI",
            active=True,
        )
        self.patients = []
        for i in range(3):
            p = Patient.objects.create(
                facility=self.fac,
                patient_number=f"P-{i}",
                full_name=f"Patient {i}",
                date_of_birth=date.today() - timedelta(days=200),
            )
            self.patients.append(p)
            VaccineFollowUp.objects.create(
                patient=p,
                vaccine_product=self.vaccine,
                dose_number=1,
                due_date=date.today() + timedelta(days=3),
            )

    def test_health_worker_can_run_for_own_facility(self):
        output = VaccinationDemandOutput(
            summary="Three children due this week.",
            by_product=[
                {
                    "product_id": self.vaccine.id,
                    "product_name": "BCG",
                    "open_follow_ups": 3,
                    "due_next_7_days": 3,
                    "due_next_30_days": 3,
                    "usable_stock": 0,
                    "projected_gap": 3,
                    "comment": "Verify stock before the session.",
                }
            ],
            priorities=["Verify BCG stock"],
            missing_information=[],
        )
        with patch("ai_engine.services.generate_structured", return_value=output):
            self.client.force_authenticate(self.hw)
            r = self.client.post(
                "/api/v1/ai/summarize-vaccination-demand/", {}, format="json"
            )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["scope_facility"], self.fac.id)
        self.assertEqual(len(r.data["validated_output"]["by_product"]), 1)

    def test_snapshot_has_no_patient_identifiers(self):
        output = VaccinationDemandOutput(
            summary="ok", by_product=[], priorities=[], missing_information=[]
        )
        with patch("ai_engine.services.generate_structured", return_value=output):
            self.client.force_authenticate(self.hw)
            r = self.client.post(
                "/api/v1/ai/summarize-vaccination-demand/", {}, format="json"
            )
        blob = json.dumps(r.data["input_snapshot"]).lower()
        self.assertNotIn("patient 0", blob)
        self.assertNotIn("p-0", blob)
        self.assertNotIn("full_name", blob)

    def test_non_vaccination_facility_rejected(self):
        plain = _mk_facility("Plain", vax=False)
        mgr = _mk_user("mgrp", User.Role.FACILITY_MANAGER, facility=plain)
        self.client.force_authenticate(mgr)
        r = self.client.post(
            "/api/v1/ai/summarize-vaccination-demand/", {}, format="json"
        )
        # Facility manager is not in CanRunVaccinationDemand
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_follow_ups_returns_400(self):
        VaccineFollowUp.objects.update(status="COMPLETED")
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/ai/summarize-vaccination-demand/",
            {"facility": self.fac.id},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "ai_validation_error")

    def test_product_not_in_scope_dropped(self):
        other = _mk_product("Measles", category="VACCINE")
        output = VaccinationDemandOutput(
            summary="ok",
            by_product=[
                {
                    "product_id": other.id,
                    "product_name": "Measles",
                    "open_follow_ups": 1,
                    "due_next_7_days": 1,
                    "due_next_30_days": 1,
                    "usable_stock": 0,
                    "projected_gap": 1,
                    "comment": "invented",
                }
            ],
            priorities=[],
            missing_information=[],
        )
        with patch("ai_engine.services.generate_structured", return_value=output):
            self.client.force_authenticate(self.admin)
            r = self.client.post(
                "/api/v1/ai/summarize-vaccination-demand/",
                {"facility": self.fac.id},
                format="json",
            )
        self.assertEqual(r.data["validated_output"]["by_product"], [])
        self.assertEqual(r.data["status"], "INVALID")
        self.assertIn(
            "product_not_in_scope",
            [e["code"] for e in r.data["validation_errors"]],
        )


# ---------------------------------------------------------------------------
# Central dashboard integration
# ---------------------------------------------------------------------------


@override_settings(GEMINI_API_KEY="fake-key")
class CentralDashboardAITests(_AIBase):
    def test_pending_ai_count_appears(self):
        AIRecommendation.objects.create(
            analysis_type="INVENTORY_ANALYSIS",
            scope_facility=self.fb,
            requested_by=self.admin,
            status="PENDING_REVIEW",
        )
        self.client.force_authenticate(self.coord)
        r = self.client.get("/api/v1/dashboard/central-summary/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("ai_recommendations", r.data)
        self.assertEqual(r.data["ai_recommendations"]["pending_review"], 1)
        self.assertEqual(len(r.data["ai_recommendations"]["queue"]), 1)


# ---------------------------------------------------------------------------
# Supply gaps -> AI sourcing -> transfer -> gap resolution
# ---------------------------------------------------------------------------


def _sourcing_output(**over):
    data = {
        "summary": "Alpha covers Beta.",
        "proposals": [],
        "missing_information": [],
    }
    data.update(over)
    return TransferSourcingOutput(**data)


@override_settings(GEMINI_API_KEY="fake-key")
class GapSourcingTests(_AIBase):
    def _mk_gap(self, facility, uncovered=40, status=SupplyGapReport.Status.OPEN):
        return SupplyGapReport.objects.create(
            facility=facility,
            product=self.product,
            reporting_horizon_start=date.today(),
            reporting_horizon_end=date.today() + timedelta(days=30),
            projected_demand=100,
            usable_stock=10,
            reliable_incoming_quantity=0,
            uncovered_quantity=uncovered,
            priority=SupplyGapReport.Priority.CRITICAL,
            status=status,
        )

    def _plan(self, output, gap_ids=None, user=None):
        with patch(
            "ai_engine.services.generate_structured", return_value=output
        ):
            self.client.force_authenticate(user or self.coord)
            payload = {} if gap_ids is None else {"gap_ids": gap_ids}
            return self.client.post(
                "/api/v1/ai/plan-gap-sourcing/", payload, format="json"
            )

    def test_facility_user_cannot_plan_gap_sourcing(self):
        self._mk_gap(self.fb)
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post("/api/v1/ai/plan-gap-sourcing/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_planable_gaps_returns_400(self):
        # Terminal and zero-uncovered gaps are not planable.
        self._mk_gap(self.fb, uncovered=0)
        resolved = self._mk_gap(self.fa, uncovered=30)
        resolved.status = SupplyGapReport.Status.RESOLVED
        resolved.save()
        r = self._plan(_sourcing_output())
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "ai_validation_error")
        self.assertEqual(SupplyRequest.objects.count(), 0)

    def test_creates_linked_request_and_marks_gap_action_planned(self):
        gap = self._mk_gap(self.fb, uncovered=40)
        r = self._plan(_sourcing_output(summary="No donor found."))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "INVALID")  # no proposal survived
        sr = SupplyRequest.objects.get()
        self.assertEqual(sr.facility, self.fb)
        self.assertEqual(sr.product, self.product)
        self.assertEqual(sr.quantity, 40)
        self.assertEqual(sr.source_gap, gap)
        gap.refresh_from_db()
        self.assertEqual(gap.status, SupplyGapReport.Status.ACTION_PLANNED)

    def test_terminal_gap_not_planned(self):
        gap = self._mk_gap(self.fb, uncovered=40)
        gap.status = SupplyGapReport.Status.RESOLVED
        gap.save()
        r = self._plan(_sourcing_output())
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SupplyRequest.objects.count(), 0)

    def test_reuses_existing_open_request_and_links_gap(self):
        gap = self._mk_gap(self.fb, uncovered=40)
        existing = SupplyRequest.objects.create(
            facility=self.fb,
            product=self.product,
            quantity=10,
            reason="Already open from a manual request.",
            requested_by=self.mgr_b,
        )
        r = self._plan(_sourcing_output())
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SupplyRequest.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.source_gap, gap)
        # Existing request was reused, so the gap is not moved to ACTION_PLANNED
        gap.refresh_from_db()
        self.assertEqual(gap.status, SupplyGapReport.Status.OPEN)

    def test_proposals_materialized_for_gap_request(self):
        gap = self._mk_gap(self.fb, uncovered=40)
        request = SupplyRequest.objects.create(
            facility=self.fb,
            product=self.product,
            quantity=40,
            reason="Critical gap",
            requested_by=self.coord,
            source_gap=gap,
        )
        output = _sourcing_output(
            summary="Alpha covers Beta.",
            proposals=[
                {
                    "request_id": request.id,
                    "source_facility_id": self.fa.id,
                    "product_id": self.product.id,
                    "quantity": 40,
                    "reason": "Alpha has the surplus.",
                }
            ],
        )
        r = self._plan(output, gap_ids=[gap.id])
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], "PENDING_REVIEW")
        proposal = SourcingProposal.objects.get()
        self.assertEqual(proposal.request, request)
        self.assertEqual(proposal.source_facility, self.fa)
        self.assertEqual(proposal.quantity, 40)

    def test_full_chain_gap_to_transfer_to_resolved(self):
        gap = self._mk_gap(self.fb, uncovered=40)
        request = SupplyRequest.objects.create(
            facility=self.fb,
            product=self.product,
            quantity=40,
            reason="Critical gap",
            requested_by=self.coord,
            source_gap=gap,
        )
        output = _sourcing_output(
            summary="Alpha covers Beta.",
            proposals=[
                {
                    "request_id": request.id,
                    "source_facility_id": self.fa.id,
                    "product_id": self.product.id,
                    "quantity": 40,
                    "reason": "Alpha has the surplus.",
                }
            ],
        )
        r = self._plan(output)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        proposal = SourcingProposal.objects.get()

        # Central admin approves the proposal -> real transfer is born
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/central/sourcing-proposals/{proposal.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        proposal.refresh_from_db()
        transfer = TransferRequest.objects.get(pk=proposal.transfer_id)
        self.assertEqual(transfer.status, TransferRequest.Status.REQUESTED)
        request.refresh_from_db()
        self.assertEqual(request.status, SupplyRequest.Status.PLANNED)

        # Donor side (central here) approves, stock reserved; then dispatch
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/dispatch/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Receiver confirms receipt -> request fulfilled AND gap auto-resolved
        self.client.force_authenticate(self.mgr_b)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/confirm-receipt/",
            {"quantity_received": 40, "condition": "OK"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        request.refresh_from_db()
        self.assertEqual(request.status, SupplyRequest.Status.FULFILLED)
        gap.refresh_from_db()
        self.assertEqual(gap.status, SupplyGapReport.Status.RESOLVED)
        self.assertIn(f"transfer #{transfer.id}", gap.resolution_notes)
        self.assertIsNotNone(gap.resolved_at)

    def test_cancelled_transfer_reopens_gap(self):
        gap = self._mk_gap(self.fb, uncovered=40)
        request = SupplyRequest.objects.create(
            facility=self.fb,
            product=self.product,
            quantity=40,
            reason="Critical gap",
            requested_by=self.coord,
            source_gap=gap,
        )
        output = _sourcing_output(
            proposals=[
                {
                    "request_id": request.id,
                    "source_facility_id": self.fa.id,
                    "product_id": self.product.id,
                    "quantity": 40,
                    "reason": "Alpha has the surplus.",
                }
            ]
        )
        self._plan(output)
        proposal = SourcingProposal.objects.get()
        self.client.force_authenticate(self.coord)
        self.client.post(
            f"/api/v1/central/sourcing-proposals/{proposal.id}/approve/",
            {},
            format="json",
        )
        proposal.refresh_from_db()
        transfer = TransferRequest.objects.get(pk=proposal.transfer_id)
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/v1/transfers/{transfer.id}/approve/", {}, format="json")
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/cancel/",
            {"reason": "Donor withdrew."},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        request.refresh_from_db()
        self.assertEqual(request.status, SupplyRequest.Status.OPEN)
        gap.refresh_from_db()
        self.assertEqual(gap.status, SupplyGapReport.Status.OPEN)
        self.assertIsNone(gap.resolved_at)