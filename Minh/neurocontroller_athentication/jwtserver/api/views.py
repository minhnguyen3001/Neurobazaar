from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import PersistentToken, ServiceToken, LoginSession
from django.utils import timezone


# REGISTER
class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email', '')

        if not username or not password:
            return Response(
                {"error": "Username and password required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already taken"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email
        )

        return Response({
            "message": f"User {username} created successfully!",
            "status": "Now you can go to /api/login/ to get your token."
        }, status=status.HTTP_201_CREATED)


# PERSISTENT LOGIN
class PersistentLoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        # 1. Authenticate user
        user = authenticate(username=username, password=password)

        if user is not None:
            # 2. Get or create persistent token
            persistent_record, created = PersistentToken.objects.get_or_create(user=user)

            # 3. Generate token if needed
            if created or not persistent_record.access_token:
                refresh = RefreshToken.for_user(user)
                persistent_record.access_token = str(refresh.access_token)
                persistent_record.save()

                message = "New token generated for first time user."
            else:
                message = "Hello, Welcome back. Existing token retrieved from database."

            # 4. Return token
            return Response({
                "access": persistent_record.access_token,
                "message": message
            }, status=status.HTTP_200_OK)

        return Response(
            {"error": "Invalid username or password"},
            status=status.HTTP_401_UNAUTHORIZED
        )

# LOGOUT
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"message": "Logout successful"},
                status=status.HTTP_205_RESET_CONTENT
            )

        except Exception:
            return Response(
                {"error": "Invalid token"},
                status=status.HTTP_400_BAD_REQUEST
            )

# REVOKE TOKEN

class AutoGlobalRevokeView(APIView):
    def post(self, request):
        # We identify the user by username or the person currently logged in
        username = request.data.get('username')

        try:
            user = User.objects.get(username=username)

            # 1. AUTO-REVOKE: Set all ServiceTokens for this user to inactive
            ServiceToken.objects.filter(user=user, is_active=True).update(
                is_active=False,
                revoked_at=timezone.now()
            )

            # 2. AUTO-REVOKE: Set all LoginSessions to inactive
            LoginSession.objects.filter(user=user, is_active=True).update(
                is_active=False,
                logged_out_at=timezone.now()
            )

            return Response({
                "status": "Security Breach Handled",
                "message": f"All tokens for {username} have been automatically revoked."
            })
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)