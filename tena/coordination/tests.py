from datetime import date, timedelta

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AuditLog, User
from coordination.models import DeliveryCoordination, SourcingProposal, SupplyGapReport, SupplyRequest
from facilities.models import Facility
from inventory.models import Product, StockBatch, TransferRequest
from inventory.services import receive_stock


def _mk_user(username, role, facility=None):
    return User.objects.create_user(
        username=username,
        password="TestPass123!",
        email=f"{username}@x.com",
        role=role,
        facility=facility,
    )


def _mk_facility(name="F"):
    return Facility.objects.create(
        name=name,
        facility_type=Facility.FacilityType.CLINIC,
        region="Addis Ababa",
        status=Facility.Status.APPROVED,
    )


def _mk_product(name="Prod"):
    return Product.objects.create(name=name, category="MEDICINE")


class DeliveryCoordinationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fa = _mk_facility("A")
        self.fb = _mk_facility("B")
        self.fc = _mk_facility("C")
        self.pharm_a = _mk_user("pa", User.Role.PHARMACIST, facility=self.fa)
        self.pharm_b = _mk_user("pb", User.Role.PHARMACIST, facility=self.fb)
        self.pharm_c = _mk_user("pc", User.Role.PHARMACIST, facility=self.fc)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.product = _mk_product()
        self.batch_a, _, _ = receive_stock(
            facility=self.fa,
            product=self.product,
            batch_number="B1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=self.pharm_a,
        )
        self.transfer = TransferRequest.objects.create(
            source_facility=self.fa,
            destination_facility=self.fb,
            product=self.product,
            source_batch=self.batch_a,
            quantity_requested=40,
            priority="HIGH",
            requested_by=self.pharm_b,
        )

    def _payload(self, **over):
        data = {
            "transport_method": "pickup",
            "transport_provider": "Local carrier",
            "contact_person_name": "Abebe",
            "contact_phone": "+251911111111",
            "transport_payer": "CENTRAL",
            "estimated_cost": "500.00",
            "delivery_status": "ARRANGED_BY_PHONE",
        }
        data.update(over)
        return data

    def test_coordinator_creates_entry(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["delivery_status"], "ARRANGED_BY_PHONE")
        self.assertEqual(r.data["transport_payer"], "CENTRAL")
        self.assertTrue(
            AuditLog.objects.filter(action="DELIVERY_COORDINATION_CREATED").exists()
        )

    def test_source_pharmacist_can_create(self):
        self.client.force_authenticate(self.pharm_a)
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_dest_pharmacist_can_create(self):
        self.client.force_authenticate(self.pharm_b)
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_unrelated_pharmacist_blocked(self):
        self.client.force_authenticate(self.pharm_c)
        r = self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/",
            self._payload(),
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_all_calls(self):
        self.client.force_authenticate(self.coord)
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/",
            self._payload(),
            format="json",
        )
        self.client.post(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/",
            self._payload(notes="Called again"),
            format="json",
        )
        r = self.client.get(
            f"/api/v1/transfers/{self.transfer.id}/delivery-coordination/"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 2)


class SupplyGapApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.fac = _mk_facility("Home")
        self.pharm = _mk_user("pharm", User.Role.PHARMACIST, facility=self.fac)
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.admin = _mk_user("admin", User.Role.SYSTEM_ADMIN)
        self.product = _mk_product("Short-Product")

        self.batch, _, _ = receive_stock(
            facility=self.fac,
            product=self.product,
            batch_number="SP-1",
            expiry_date=date.today() + timedelta(days=180),
            quantity=100,
            performed_by=self.pharm,
        )
        # Burn down usage so there is a real shortage
        from inventory.services import consume_stock

        consume_stock(batch=self.batch, quantity=90, performed_by=self.pharm)
        # 10 usable, 3/day * 30 = 90 demand → gap 80

    def test_non_central_cannot_list(self):
        self.client.force_authenticate(self.pharm)
        r = self.client.get("/api/v1/central/supply-gaps/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_refresh_creates_gaps(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post("/api/v1/central/supply-gaps/refresh/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(r.data["created"], 1)
        self.assertGreaterEqual(r.data["active_count"], 1)
        report = SupplyGapReport.objects.filter(facility=self.fac).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.status, "OPEN")
        self.assertGreater(report.uncovered_quantity, 0)

    def test_refresh_updates_existing(self):
        self.client.force_authenticate(self.coord)
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        first_count = SupplyGapReport.objects.count()
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        self.assertEqual(SupplyGapReport.objects.count(), first_count)

    def test_refresh_only_affects_specified_facility(self):
        other_fac = _mk_facility("Other")
        other_batch, _, _ = receive_stock(
            facility=other_fac,
            product=self.product,
            batch_number="SP-O",
            expiry_date=date.today() + timedelta(days=180),
            quantity=5,
            performed_by=_mk_user("pother", User.Role.PHARMACIST, facility=other_fac),
        )
        from inventory.services import consume_stock

        consume_stock(batch=other_batch, quantity=3, performed_by=self.pharm)

        self.client.force_authenticate(self.coord)
        self.client.post(
            f"/api/v1/central/supply-gaps/refresh/?facility={self.fac.id}"
        )
        self.assertTrue(
            SupplyGapReport.objects.filter(facility=self.fac).exists()
        )
        self.assertFalse(
            SupplyGapReport.objects.filter(facility=other_fac).exists()
        )

    def test_assign(self):
        self.client.force_authenticate(self.coord)
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        gap = SupplyGapReport.objects.filter(facility=self.fac).first()
        self.assertIsNotNone(gap)
        r = self.client.post(
            f"/api/v1/central/supply-gaps/{gap.id}/assign/",
            {"assigned_to": self.coord.id, "note": "Will coordinate"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        gap.refresh_from_db()
        self.assertEqual(gap.status, "ASSIGNED")
        self.assertEqual(gap.assigned_to, self.coord)

    def test_escalate(self):
        self.client.force_authenticate(self.coord)
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        gap = SupplyGapReport.objects.filter(facility=self.fac).first()
        r = self.client.post(
            f"/api/v1/central/supply-gaps/{gap.id}/escalate/",
            {"note": "Beyond redistribution"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        gap.refresh_from_db()
        self.assertEqual(gap.status, "ESCALATED")

    def test_cannot_escalate_twice(self):
        self.client.force_authenticate(self.coord)
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        gap = SupplyGapReport.objects.filter(facility=self.fac).first()
        self.client.post(f"/api/v1/central/supply-gaps/{gap.id}/escalate/", {}, format="json")
        r = self.client.post(f"/api/v1/central/supply-gaps/{gap.id}/escalate/", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_resolve(self):
        self.client.force_authenticate(self.coord)
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        gap = SupplyGapReport.objects.filter(facility=self.fac).first()
        r = self.client.post(
            f"/api/v1/central/supply-gaps/{gap.id}/resolve/",
            {"resolution_notes": "Delivered from central warehouse"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        gap.refresh_from_db()
        self.assertEqual(gap.status, "RESOLVED")
        self.assertIsNotNone(gap.resolved_at)

    def test_refresh_after_resolve_creates_new_report(self):
        self.client.force_authenticate(self.coord)
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        gap = SupplyGapReport.objects.filter(facility=self.fac).first()
        self.client.post(
            f"/api/v1/central/supply-gaps/{gap.id}/resolve/",
            {"resolution_notes": "Done"},
            format="json",
        )
        # The shortage still exists in reality — refresh should create a new report
        self.client.post("/api/v1/central/supply-gaps/refresh/")
        active = SupplyGapReport.objects.filter(
            facility=self.fac,
            status__in=SupplyGapReport.NON_TERMINAL_STATUSES,
        )
        self.assertEqual(active.count(), 1)
        self.assertNotEqual(active.first().id, gap.id)

    def test_admin_can_access(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/central/supply-gaps/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)


class SupplyGapPriorityTests(TestCase):
    def _mk_and_consume(self, quantity_received, quantity_consumed):
        fac = _mk_facility(f"P{quantity_received}")
        pharm = _mk_user(f"p{quantity_received}", User.Role.PHARMACIST, facility=fac)
        product = _mk_product(f"Pr{quantity_received}")
        _, batch, _ = receive_stock(
            facility=fac,
            product=product,
            batch_number="PX",
            expiry_date=date.today() + timedelta(days=180),
            quantity=quantity_received,
            performed_by=pharm,
        )
        from inventory.services import consume_stock

        if quantity_consumed > 0:
            consume_stock(
                batch=batch, quantity=quantity_consumed, performed_by=pharm
            )
        return fac, product

    def test_critical_when_days_of_stock_under_7(self):
        # 3/day usage, 15 stock → 5 days
        fac, product = self._mk_and_consume(105, 90)
        from coordination.services import upsert_supply_gap

        report, _ = upsert_supply_gap(facility=fac, product=product)
        self.assertIsNotNone(report)
        self.assertEqual(report.priority, "CRITICAL")

# ---------------------------------------------------------------------------
# AI sourcing proposals -> real transfers (facility request workflow)
# ---------------------------------------------------------------------------


class SourcingProposalFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coord = _mk_user("coord", User.Role.CENTRAL_COORDINATOR)
        self.src_mgr = _mk_user("srcmgr", User.Role.FACILITY_MANAGER)
        self.src2_mgr = _mk_user("src2mgr", User.Role.FACILITY_MANAGER)
        self.dst_mgr = _mk_user("dstmgr", User.Role.FACILITY_MANAGER)
        self.src = _mk_facility("Donor One")
        self.src2 = _mk_facility("Donor Two")
        self.dst = _mk_facility("Requester")
        for u, f in (
            (self.src_mgr, self.src),
            (self.src2_mgr, self.src2),
            (self.dst_mgr, self.dst),
        ):
            u.facility = f
            u.save()
        self.product = _mk_product("Ceftriaxone")
        self.batch, _, _ = receive_stock(
            facility=self.src,
            product=self.product,
            batch_number="D-1",
            expiry_date=date.today() + timedelta(days=200),
            quantity=500,
            performed_by=self.src_mgr,
        )
        self.request = SupplyRequest.objects.create(
            facility=self.dst,
            product=self.product,
            quantity=46,
            reason="Critical gap",
            requested_by=self.dst_mgr,
        )
        self.proposal = SourcingProposal.objects.create(
            request=self.request,
            source_facility=self.src,
            product=self.product,
            quantity=46,
            reason="Largest eligible surplus.",
        )

    def _approve_proposal(self):
        self.client.force_authenticate(self.coord)
        return self.client.post(
            f"/api/v1/central/sourcing-proposals/{self.proposal.id}/approve/",
            {"note": "Go with Donor One"},
            format="json",
        )

    def test_facility_cannot_list_proposals(self):
        self.client.force_authenticate(self.dst_mgr)
        r = self.client.get("/api/v1/central/sourcing-proposals/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_facility_cannot_approve_proposal(self):
        self.client.force_authenticate(self.src_mgr)
        r = self.client.post(
            f"/api/v1/central/sourcing-proposals/{self.proposal.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_creates_high_priority_transfer(self):
        r = self._approve_proposal()
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.proposal.refresh_from_db()
        self.request.refresh_from_db()
        self.assertEqual(self.proposal.status, SourcingProposal.Status.APPROVED)
        self.assertEqual(self.request.status, SupplyRequest.Status.PLANNED)
        transfer = TransferRequest.objects.get(pk=self.proposal.transfer_id)
        self.assertEqual(transfer.source_facility, self.src)
        self.assertEqual(transfer.destination_facility, self.dst)
        self.assertEqual(transfer.status, TransferRequest.Status.REQUESTED)
        self.assertEqual(transfer.priority, TransferRequest.Priority.HIGH)
        self.assertTrue(
            AuditLog.objects.filter(action="SOURCING_PROPOSAL_APPROVED").exists()
        )

    def test_approve_supersedes_alternative_proposals(self):
        alt = SourcingProposal.objects.create(
            request=self.request,
            source_facility=self.src2,
            product=self.product,
            quantity=46,
            reason="Alternative source.",
        )
        r = self._approve_proposal()
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        alt.refresh_from_db()
        self.assertEqual(alt.status, SourcingProposal.Status.REJECTED)
        self.assertIn("Superseded", alt.review_note)

    def test_cannot_approve_twice(self):
        self._approve_proposal()
        r = self._approve_proposal()
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_reject_requires_note(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/central/sourcing-proposals/{self.proposal.id}/reject/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_keeps_request_open(self):
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/central/sourcing-proposals/{self.proposal.id}/reject/",
            {"note": "Donor cannot spare stock."},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.proposal.refresh_from_db()
        self.request.refresh_from_db()
        self.assertEqual(self.proposal.status, SourcingProposal.Status.REJECTED)
        self.assertEqual(self.request.status, SupplyRequest.Status.OPEN)

    def _approved_transfer(self):
        self._approve_proposal()
        self.proposal.refresh_from_db()
        return TransferRequest.objects.get(pk=self.proposal.transfer_id)

    def test_receive_transfer_fulfills_request(self):
        transfer = self._approved_transfer()
        self.client.force_authenticate(self.src_mgr)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/approve/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/dispatch/", {}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.dst_mgr)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/confirm-receipt/",
            {"quantity_received": 46, "condition": "OK"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, SupplyRequest.Status.FULFILLED)

    def _link_gap(self):
        gap = SupplyGapReport.objects.create(
            facility=self.dst,
            product=self.product,
            reporting_horizon_start=date.today(),
            reporting_horizon_end=date.today() + timedelta(days=30),
            projected_demand=100,
            usable_stock=10,
            reliable_incoming_quantity=0,
            uncovered_quantity=46,
            priority="CRITICAL",
        )
        self.request.source_gap = gap
        self.request.save(update_fields=["source_gap"])
        return gap

    def test_receive_transfer_resolves_linked_gap(self):
        gap = self._link_gap()
        transfer = self._approved_transfer()
        self.client.force_authenticate(self.src_mgr)
        self.client.post(f"/api/v1/transfers/{transfer.id}/approve/", {}, format="json")
        self.client.force_authenticate(self.coord)
        self.client.post(f"/api/v1/transfers/{transfer.id}/dispatch/", {}, format="json")
        self.client.force_authenticate(self.dst_mgr)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/confirm-receipt/",
            {"quantity_received": 46, "condition": "OK"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        gap.refresh_from_db()
        self.assertEqual(gap.status, SupplyGapReport.Status.RESOLVED)
        self.assertIn(f"transfer #{transfer.id}", gap.resolution_notes)
        self.assertIsNotNone(gap.resolved_at)

    def test_gap_serializer_exposes_active_request(self):
        gap = self._link_gap()
        self.client.force_authenticate(self.coord)
        r = self.client.get(f"/api/v1/central/supply-gaps/{gap.id}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        active = r.data["active_request"]
        self.assertEqual(active["id"], self.request.id)
        self.assertEqual(active["status"], "OPEN")
        self.assertEqual(active["quantity"], 46)
        self.assertEqual(active["proposal_status"], "PROPOSED")
        self.assertIsNone(active["transfer_id"])

    def test_cancel_transfer_reopens_request(self):
        transfer = self._approved_transfer()
        self.client.force_authenticate(self.src_mgr)
        self.client.post(f"/api/v1/transfers/{transfer.id}/approve/", {}, format="json")
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/cancel/",
            {"reason": "Donor withdrew."},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.proposal.refresh_from_db()
        self.request.refresh_from_db()
        self.assertEqual(self.proposal.status, SourcingProposal.Status.PROPOSED)
        self.assertIsNone(self.proposal.transfer_id)
        self.assertEqual(self.request.status, SupplyRequest.Status.OPEN)

    def test_cancel_transfer_reopens_linked_gap(self):
        gap = self._link_gap()
        transfer = self._approved_transfer()
        self.client.force_authenticate(self.src_mgr)
        self.client.post(f"/api/v1/transfers/{transfer.id}/approve/", {}, format="json")
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            f"/api/v1/transfers/{transfer.id}/cancel/",
            {"reason": "Donor withdrew."},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        gap.refresh_from_db()
        self.assertEqual(gap.status, SupplyGapReport.Status.OPEN)
        self.assertIsNone(gap.resolved_at)

    def test_cancelled_request_blocks_approval(self):
        self.request.status = SupplyRequest.Status.CANCELLED
        self.request.save()
        r = self._approve_proposal()
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
