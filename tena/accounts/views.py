from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .serializers import RegisterSerializer, UserSerializer
from .services import log_audit
from drf_spectacular.utils import extend_schema

class MedBridgeTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role + facility_id into the JWT so clients avoid an extra call."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["facility_id"] = user.facility_id
        return token

@extend_schema(tags=["Auth"])
class MedBridgeTokenObtainPairView(TokenObtainPairView):
    serializer_class = MedBridgeTokenObtainPairSerializer

@extend_schema(tags=["Auth"])
class RegisterView(APIView):
    """Public account creation for facility applicants.

    The account starts with no facility and the default HEALTH_WORKER role;
    approving the applicant's facility application promotes them to
    FACILITY_MANAGER of that facility.
    """

    permission_classes = [AllowAny]
    throttle_scope = "register"

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        log_audit(
            user,
            "USER_REGISTERED",
            "User",
            user.id,
            metadata={"role": user.role},
            ip_address=_ip(request),
        )
        refresh = MedBridgeTokenObtainPairSerializer.get_token(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Auth"])
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


def _ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")