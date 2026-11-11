from django.contrib.auth.password_validation import validate_password as validate_django_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(
        source="actor.username", read_only=True, default=None
    )
    actor_role = serializers.CharField(source="actor.role", read_only=True, default=None)
    actor_facility_name = serializers.CharField(
        source="actor.facility.name", read_only=True, default=None
    )

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "actor_username",
            "actor_role",
            "actor_facility_name",
            "action",
            "entity_type",
            "entity_id",
            "metadata",
            "ip_address",
            "created_at",
        )
        read_only_fields = fields

class UserSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    facility_status = serializers.CharField(source="facility.status", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "facility",
            "facility_name",
            "facility_status",
            "is_active",
            "date_joined",
        )
        read_only_fields = (
            "id",
            "date_joined",
            "facility_name",
            "facility_status",
        )



class RegisterSerializer(serializers.ModelSerializer):
    """Public self-registration; always creates a facility-less health worker.

    Privileged roles are never accepted here. Facility association and the
    FACILITY_MANAGER role are granted by the application approval workflow.
    """

    password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "password",
            "password_confirm",
        )

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": ["Passwords do not match."]}
            )
        candidate = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_django_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(role=User.Role.HEALTH_WORKER, **validated_data)
        user.set_password(password)
        user.save()
        return user


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Used by facility managers / system admins to create facility-scoped users.
    Never exposes password in the response.
    """

    FACILITY_ROLES = {
        User.Role.FACILITY_MANAGER,
        User.Role.PHARMACIST,
        User.Role.INVENTORY_STAFF,
        User.Role.PHARMACY_STAFF,
        User.Role.HEALTH_WORKER,
    }

    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "password",
        )

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_role(self, value):
        if value not in self.FACILITY_ROLES:
            raise serializers.ValidationError(
                "Only facility-scoped roles can be created here."
            )
        request = self.context.get("request")
        if value == User.Role.FACILITY_MANAGER:
            if not request or request.user.role != User.Role.SYSTEM_ADMIN:
                raise serializers.ValidationError(
                    "Only system admins can assign the FACILITY_MANAGER role."
                )
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        facility = self.context.get("facility")
        user = User(**validated_data)
        if facility is not None:
            user.facility = facility
        user.set_password(password)
        user.save()
        return user