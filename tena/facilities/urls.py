from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    FacilityApplicationViewSet,
    FacilityUserViewSet,
    FacilityViewSet,
)

router = DefaultRouter()
# Register applications FIRST so /facilities/applications/ wins over /facilities/{pk}/.
router.register("applications", FacilityApplicationViewSet, basename="facility-application")
router.register("", FacilityViewSet, basename="facility")

facility_users_list = FacilityUserViewSet.as_view({"get": "list", "post": "create"})
facility_user_deactivate = FacilityUserViewSet.as_view({"post": "deactivate"})

urlpatterns = [
    path("<int:facility_pk>/users/", facility_users_list, name="facility-users"),
    path(
        "<int:facility_pk>/users/<int:pk>/deactivate/",
        facility_user_deactivate,
        name="facility-user-deactivate",
    ),
    path("", include(router.urls)),
]