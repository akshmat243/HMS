from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.auth import authenticate, logout, login
from rest_framework.permissions import IsAuthenticated
from MBP.permissions import HasModelPermission
from MBP.models import Role, RoleModelPermission
from accounts.serializers import UserSerializer, RegisterUserSerializer
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from MBP.utils import log_audit
from rest_framework.permissions import AllowAny
from MBP.views import ProtectedModelViewSet
from django.core.mail import send_mail
from django.conf import settings
import random
from django.contrib.auth import get_user_model

User = get_user_model()

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import UserRateThrottle

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter

class UserViewSet(ProtectedModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    model_name = 'User'
    lookup_field = 'slug'

    def get_permissions(self):
        if self.request.user.is_superuser:
            return [IsAuthenticated()]

        self.permission_code = {
            'create': 'c',
            'update': 'u',
            'partial_update': 'u',
            'destroy': 'd',
        }.get(self.action, 'r')

        return [HasModelPermission()]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return User.objects.all().order_by('-date_joined')
        return User.objects.filter(created_by=user).order_by('-date_joined')

    @action(detail=True, methods=['patch'], url_path='assign-role', permission_classes=[HasModelPermission])
    def assign_role(self, request, slug=None):
        try:
            user = self.get_object()

            role_slug = request.data.get('role_slug')
            if not role_slug:
                return Response({"error": "role_slug is required."}, status=status.HTTP_400_BAD_REQUEST)

            role = Role.objects.get(slug=role_slug)

            user.role = role
            user.is_active = True
            user._request_user = request.user
            user.save()

            log_audit(
                request=request,
                action='update',
                model_name='User',
                object_id=user.pk,
                details=f"Assigned role '{role.name}' and activated user {user.email}",
                new_data={"role": role.name, "is_active": True}
            )

            return Response({"message": "Role assigned and user activated."}, status=status.HTTP_200_OK)

        except Role.DoesNotExist:
            return Response({"error": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

from django.core.cache import cache

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterUserSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            user = serializer.save()

            # # ✅ Generate OTP for phone
            # otp = str(random.randint(100000, 999999))
            
            # # ✅ Store OTP in cache for 5 min
            # cache.set(f"otp_{user.phone}", otp, timeout=300)
            # print(f"DEBUG: OTP for {user.phone} is {otp}")  # Replace with Twilio SMS later

            # ✅ Send email verification
            verification_link = f"http://127.0.0.1:8000/api/verify-email/{user.slug}/"
            send_mail(
                subject="Verify your email",
                message=f"Hello {user.full_name},\n\nClick here to verify your email: {verification_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            # 🔐 Audit log
            log_audit(
                request=request,
                action="create",
                model_name="User",
                object_id=user.id,
                details=f"User {user.email} registered manually. Email + OTP pending.",
                new_data=serializer.data,
            )

            return Response(
                {
                    "message": "Registered successfully. Please verify your email",
                    "user_name": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request, slug):
        user = get_object_or_404(User, slug=slug)
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save()
        return Response(
            {"message": "Email verified successfully!"},
            status=status.HTTP_200_OK
        )

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        phone = request.data.get("phone")
        otp = request.data.get("otp")

        stored_otp = cache.get(f"otp_{phone}")

        if not stored_otp:
            return Response({"error": "No OTP found. Please register again."}, status=status.HTTP_400_BAD_REQUEST)

        if str(stored_otp) != str(otp):
            return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(User, phone=phone)
        if not user.is_phone_verified:
            user.is_phone_verified = True
            user.save()

        cache.delete(f"otp_{phone}")

        return Response(
            {"message": "Phone verified successfully!"},
            status=status.HTTP_200_OK
        )


class LoginView(APIView):
    permission_classes = []  # login is public
    throttle_classes = [UserRateThrottle]  # prevent brute force

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 1: Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Step 2: Check password
        if not user.check_password(password):
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Step 3: Check email verification
        if not user.is_email_verified:
            return Response(
                {"error": "Please verify your email before logging in."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Step 4: Check phone verification
        if not user.is_phone_verified:
            return Response(
                {"error": "Please verify your phone number via OTP."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Step 5: Check if account is active
        if not user.is_active:
            return Response(
                {"error": "Account is inactive. Contact support if this persists."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Step 6: Issue JWT tokens
        refresh = RefreshToken.for_user(user)

        # Step 7: Audit log
        log_audit(
            request=request,
            action="login",
            model_name="User",
            object_id=user.id,
            details=f"{user.email} logged in"
        )

        # Step 8: Collect permissions for role
        role = user.role
        accessible_models = []
        if role:
            role_perms = RoleModelPermission.objects.filter(role=role)
            for rp in role_perms:
                accessible_models.append({
                    "model_name": rp.model.name,
                    "permission": rp.permission_type.code
                })

        # Step 9: Return response
        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                # "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.name if user.role else None,
                "permissions": accessible_models,
            },
        }, status=status.HTTP_200_OK)
        
                
from rest_framework_simplejwt.tokens import TokenError, AccessToken
from django.core.cache import cache
import datetime


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        access_token = request.headers.get("Authorization", "").split(" ")[1]  # Extract access token

        if not refresh_token:
            return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Blacklist refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()

            # Blacklist access token by adding its jti to cache
            access = AccessToken(access_token)
            jti = access['jti']
            exp = access['exp']

            # Calculate expiry time from token
            expiry_time = datetime.datetime.fromtimestamp(exp) - datetime.datetime.now()
            cache.set(f"blacklisted_{jti}", True, timeout=expiry_time.total_seconds())

            log_audit(
                request=request,
                action='logout',
                model_name='User',
                object_id=request.user.id,
                details=f"{request.user.email} logged out."
            )

            return Response({"message": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)

        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




# class LoginView(APIView):
#     permission_classes = []

#     def post(self, request):
#         login_type = request.data.get("login_type", "simple")  # 'simple' or 'oauth'

#         if login_type == "simple":
#             email = request.data.get("email")
#             password = request.data.get("password")
#             user = authenticate(request, email=email, password=password)

#             if not user:
#                 return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

#         elif login_type == "oauth":
#             email = request.data.get("email")
#             try:
#                 user = User.objects.get(email=email)
#             except User.DoesNotExist:
#                 return Response({"error": "User not found. Please register first."}, status=status.HTTP_404_NOT_FOUND)

#         else:
#             return Response({"error": "Invalid login type."}, status=status.HTTP_400_BAD_REQUEST)

#         if not user.is_active:
#             return Response({"error": "Account is inactive."}, status=status.HTTP_403_FORBIDDEN)

#         login(request, user)

#         log_audit(
#             request=request,
#             action='login',
#             model_name='User',
#             object_id=user.id,
#             details=f"{user.email} logged in via {login_type}"
#         )

#         # Role-based permission info
#         role = user.role
#         accessible_models = []
#         if role:
#             role_perms = RoleModelPermission.objects.filter(role=role)
#             for rp in role_perms:
#                 model_info = {
#                     "model_name": rp.model.name,
#                     "permission": rp.permission_type.code
#                 }
#                 accessible_models.append(model_info)

#         return Response({
#             "message": "Login successful.",
#             "user": {
#                 "id": str(user.id),
#                 "email": user.email,
#                 "full_name": user.full_name,
#                 "role": user.role.name if user.role else None,
#                 "permissions": accessible_models
#             }
#         }, status=status.HTTP_200_OK)


# class LogoutView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         log_audit(
#             request=request,
#             action='logout',
#             model_name='User',
#             object_id=request.user.id,
#             details=f"{request.user.email} logged out."
#         )

#         logout(request)

#         return Response({"message": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .gemini_utils import generate_text

class GeminiTextAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        prompt = request.data.get("prompt", "")
        if not prompt:
            return Response({"error": "Prompt is required"}, status=400)
        
        generated_text = generate_text(prompt)
        return Response({"result": generated_text})
