from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.services import log_audit
from facilities.models import Facility

from .models import AIRecommendation
from .permissions import *
from .serializers import *
from .services import *

from drf_spectacular.utils import extend_schema

CENTRAL_ROLES = {User.Role.SYSTEM_ADMIN, User.Role.CENTRAL_COORDINATOR}


def _ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _resolve_facility(request, facility_id):
    """Central users may target any facility or none; others are pinned to their own."""
    user = request.user
    if user.role in CENTRAL_ROLES:
        if facility_id is None:
            return None
        try:
            return Facility.objects.get(pk=facility_id)
        except Facility.DoesNotExist:
            raise NotFound("Facility not found.")

    if not user.facility_id:
        raise PermissionDenied("You are not assigned to a facility.")
    if facility_id is not None and facility_id != user.facility_id:
        raise PermissionDenied("You cannot analyse another facility.")
    if user.facility.status != "APPROVED" or not user.facility.is_active:
        raise PermissionDenied("Your facility is not operational.")
    return user.facility


@extend_schema(
    tags=["AI"],
    request=AnalyzeInventoryRequestSerializer,
    responses={201: AIRecommendationDetailSerializer},
    description=(
        "Run Gemini inventory analysis. Returns an AIRecommendation record. "
        "The AI never writes stock or creates transfers — its output is "
        "advisory and requires review via `/ai/recommendations/{id}/approve/`."
    ),
)
class AnalyzeInventoryView(APIView):
    permission_classes = [IsAuthenticated, CanRunInventoryAnalysis]
    throttle_scope = "ai"

    def post(self, request):
        ser = AnalyzeInventoryRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        facility = _resolve_facility(request, ser.validated_data.get("facility"))

        try:
            recommendation = analyze_inventory(
                user=request.user,
                facility=facility,
                horizon_days=ser.validated_data["horizon_days"],
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "ai_validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit(
            request.user,
            "AI_ANALYSIS_REQUESTED",
            "AIRecommendation",
            recommendation.id,
            metadata={
                "analysis_type": recommendation.analysis_type,
                "status": recommendation.status,
                "scope_facility_id": recommendation.scope_facility_id,
            },
            ip_address=_ip(request),
        )
        return Response(
            AIRecommendationDetailSerializer(recommendation).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["AI"],
    request=PrioritizeGapsRequestSerializer,
    responses={201: AIRecommendationDetailSerializer},
)
class PrioritizeSupplyGapsView(APIView):
    permission_classes = [IsAuthenticated, CanRunGapPrioritization]
    throttle_scope = "ai"

    def post(self, request):
        ser = PrioritizeGapsRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            recommendation = prioritize_supply_gaps(
                user=request.user,
                horizon_days=ser.validated_data["horizon_days"],
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "ai_validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit(
            request.user,
            "AI_ANALYSIS_REQUESTED",
            "AIRecommendation",
            recommendation.id,
            metadata={"analysis_type": recommendation.analysis_type},
            ip_address=_ip(request),
        )
        return Response(
            AIRecommendationDetailSerializer(recommendation).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["AI"],
    request=SummarizeVaccinationRequestSerializer,
    responses={201: AIRecommendationDetailSerializer},
)
class SummarizeVaccinationDemandView(APIView):
    permission_classes = [IsAuthenticated, CanRunVaccinationDemand]
    throttle_scope = "ai"

    def post(self, request):
        ser = SummarizeVaccinationRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        facility = _resolve_facility(request, ser.validated_data.get("facility"))
        if facility is None:
            return Response(
                {
                    "detail": "facility is required for vaccination demand summaries.",
                    "code": "facility_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not facility.provides_vaccination_services:
            return Response(
                {
                    "detail": "Facility does not provide vaccination services.",
                    "code": "not_a_vaccination_facility",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            recommendation = summarize_vaccination_demand(
                user=request.user,
                facility=facility,
                horizon_days=ser.validated_data["horizon_days"],
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "ai_validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit(
            request.user,
            "AI_ANALYSIS_REQUESTED",
            "AIRecommendation",
            recommendation.id,
            metadata={
                "analysis_type": recommendation.analysis_type,
                "scope_facility_id": recommendation.scope_facility_id,
            },
            ip_address=_ip(request),
        )
        return Response(
            AIRecommendationDetailSerializer(recommendation).data,
            status=status.HTTP_201_CREATED,
        )

@extend_schema(
    tags=["AI"],
    request=PlanSourcingRequestSerializer,
    responses={201: AIRecommendationDetailSerializer},
    description=(
        "Plan donor transfers for open supply requests (central only). "
        "Gemini proposes one donor transfer per fillable request; validated "
        "proposals are materialised for review at "
        "`/central/sourcing-proposals/`. Approving a proposal creates the "
        "real transfer request to the donor facility."
    ),
)
class PlanTransferSourcingView(APIView):
    permission_classes = [IsAuthenticated, CanRunTransferSourcing]
    throttle_scope = "ai"

    def post(self, request):
        ser = PlanSourcingRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            recommendation = plan_transfer_sourcing(
                user=request.user,
                supply_request_ids=ser.validated_data.get("supply_request_ids"),
                horizon_days=ser.validated_data["horizon_days"],
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "ai_validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit(
            request.user,
            "AI_ANALYSIS_REQUESTED",
            "AIRecommendation",
            recommendation.id,
            metadata={
                "analysis_type": recommendation.analysis_type,
                "status": recommendation.status,
            },
            ip_address=_ip(request),
        )
        return Response(
            AIRecommendationDetailSerializer(recommendation).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["AI"],
    request=PlanGapSourcingSerializer,
    responses={201: AIRecommendationDetailSerializer},
    description=(
        "Plan donor transfers for open supply gaps (central only). Each gap "
        "gets (or reuses) an open supply request, then Gemini proposes donor "
        "facilities; validated proposals are materialised for review at "
        "`/central/sourcing-proposals/`. Approving a proposal creates the "
        "real transfer request to the donor facility."
    ),
)
class PlanGapSourcingView(APIView):
    permission_classes = [IsAuthenticated, CanRunTransferSourcing]
    throttle_scope = "ai"

    def post(self, request):
        ser = PlanGapSourcingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            recommendation = plan_gap_sourcing(
                user=request.user,
                gap_ids=ser.validated_data.get("gap_ids"),
                horizon_days=ser.validated_data["horizon_days"],
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "ai_validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit(
            request.user,
            "AI_ANALYSIS_REQUESTED",
            "AIRecommendation",
            recommendation.id,
            metadata={
                "analysis_type": recommendation.analysis_type,
                "status": recommendation.status,
            },
            ip_address=_ip(request),
        )
        return Response(
            AIRecommendationDetailSerializer(recommendation).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["AI"])
class AIRecommendationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_fields = ("analysis_type", "status", "scope_facility")
    ordering_fields = ("created_at", "status")
    ordering = ("-created_at",)
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AIRecommendationDetailSerializer
        return AIRecommendationSerializer

    def get_queryset(self):
        user = self.request.user
        qs = AIRecommendation.objects.select_related(
            "scope_facility", "requested_by", "reviewed_by"
        )
        if user.role in CENTRAL_ROLES:
            return qs
        if user.role == User.Role.FACILITY_MANAGER and user.facility_id:
            return qs.filter(scope_facility_id=user.facility_id)
        if user.role in (User.Role.PHARMACIST, User.Role.INVENTORY_STAFF):
            if user.facility_id:
                return qs.filter(
                    scope_facility_id=user.facility_id,
                    analysis_type=AIRecommendation.AnalysisType.INVENTORY_ANALYSIS,
                )
            return qs.none()
        if user.role == User.Role.HEALTH_WORKER and user.facility_id:
            return qs.filter(
                scope_facility_id=user.facility_id,
                analysis_type=AIRecommendation.AnalysisType.VACCINATION_DEMAND_SUMMARY,
            )
        return qs.none()

    def _assert_can_review(self, recommendation, user):
        if recommendation.status != AIRecommendation.Status.PENDING_REVIEW:
            raise PermissionDenied(
                f"Recommendation is already {recommendation.status}."
            )
        if user.role in CENTRAL_ROLES:
            return
        if (
            user.role == User.Role.FACILITY_MANAGER
            and user.facility_id
            and recommendation.scope_facility_id == user.facility_id
        ):
            return
        raise PermissionDenied("You cannot review this recommendation.")

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, CanReviewRecommendation],
    )
    def approve(self, request, pk=None):
        recommendation = self.get_object()
        self._assert_can_review(recommendation, request.user)

        ser = ReviewActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            recommendation = approve_recommendation(
                recommendation=recommendation,
                reviewer=request.user,
                note=ser.validated_data.get("note", ""),
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )

        log_audit(
            request.user,
            "AI_RECOMMENDATION_APPROVED",
            "AIRecommendation",
            recommendation.id,
            metadata={"analysis_type": recommendation.analysis_type},
            ip_address=_ip(request),
        )
        return Response(AIRecommendationDetailSerializer(recommendation).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, CanReviewRecommendation],
    )
    def reject(self, request, pk=None):
        recommendation = self.get_object()
        self._assert_can_review(recommendation, request.user)

        ser = RejectActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            recommendation = reject_recommendation(
                recommendation=recommendation,
                reviewer=request.user,
                note=ser.validated_data["note"],
            )
        except AIValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_state"},
                status=status.HTTP_409_CONFLICT,
            )

        log_audit(
            request.user,
            "AI_RECOMMENDATION_REJECTED",
            "AIRecommendation",
            recommendation.id,
            metadata={"note": ser.validated_data["note"]},
            ip_address=_ip(request),
        )
        return Response(AIRecommendationDetailSerializer(recommendation).data)