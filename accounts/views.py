from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.auth import authenticate, logout, login
from rest_framework.permissions import IsAuthenticated
from MBP.permissions import HasModelPermission
from MBP.models import Role, RoleModelPermission
from accounts.serializers import UserSerializer, RegisterUserSerializer
from rest_framework.views import APIView
from MBP.utils import log_audit
from MBP.views import ProtectedModelViewSet
from django.contrib.auth import get_user_model

User = get_user_model()

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import UserRateThrottle



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


class RegisterView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = RegisterUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            log_audit(
                request=request,
                action='create',
                model_name='User',
                object_id=user.id,
                details=f"User {user.email} registered manually.",
                new_data=serializer.data
            )
            
            return Response({
                "message": "Registered successfully. Awaiting admin approval.",
                "user_id": user.id
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = []
    throttle_classes = [UserRateThrottle]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None:
            if not user.is_active:
                return Response({"error": "Account is inactive."}, status=status.HTTP_403_FORBIDDEN)

            refresh = RefreshToken.for_user(user)

            log_audit(
                request=request,
                action='login',
                model_name='User',
                object_id=user.id,
                details=f"{user.email} logged in"
            )
            # Fetch accessible models for this user
            role = user.role
            accessible_models = []
            if role:
                role_perms = RoleModelPermission.objects.filter(role=role)
                for rp in role_perms:
                    model_info = {
                        "model_name": rp.model.name,
                        "permission": rp.permission_type.code  # 'c', 'r', 'u', 'd'
                    }
                    accessible_models.append(model_info)

            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.name if user.role else None,
                    "permissions": accessible_models
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            log_audit(
                request=request,
                action='logout',
                model_name='User',
                object_id=request.user.id,
                details=f"{request.user.email} logged out."
            )
            
            return Response({"message": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": "Invalid token or already blacklisted."}, status=status.HTTP_400_BAD_REQUEST)




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