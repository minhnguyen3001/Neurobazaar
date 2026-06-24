from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,

)
from api.views import RegisterView, PersistentLoginView, LogoutView

urlpatterns = [

    # REGISTER INTERFACE: It use for register first time user
    path('api/register/', RegisterView.as_view(), name='auth_register'),
    # LOGIN INTERFACE: Returns Access and Refresh tokens
    path('api/login/', PersistentLoginView.as_view(), name='persistent_login'),

    # REFRESH INTERFACE: Exchanges Refresh for a new Access token
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # LOGOUT INTERFACE: Blacklists the token so it can't be used again
    path('api/logout/', TokenBlacklistView.as_view(), name='token_blacklist'),


]