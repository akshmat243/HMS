from MBP.views import ProtectedModelViewSet
from .models import Staff, Attendance, Payroll, Leave, StaffDocument
from .serializers import StaffSerializer, AttendanceSerializer, PayrollSerializer, LeaveSerializer, StaffDocumentSerializer , StaffDashboardOverviewSerializer 
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import time
from django.utils import timezone
from rest_framework import status
from django.db.models import Count, Q, F, Avg, Sum
from django.db import transaction
from Hotel.models import Hotel
from Restaurant.models import Restaurant

class StaffDocumentViewSet(ProtectedModelViewSet):
    queryset = StaffDocument.objects.select_related(
        "staff", "staff__hotel", "staff__restaurant", "staff__user"
    )
    serializer_class = StaffDocumentSerializer
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 1️⃣ Superuser → all documents
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → staff documents of their hotel OR restaurant
        if role_name == "admin":
            # Hotel admin
            hotel = Hotel.objects.filter(owner=user).first()
            if hotel:
                qs = qs.filter(staff__hotel=hotel)

            # Restaurant admin
            restaurant = Restaurant.objects.filter(owner=user).first()
            if restaurant:
                qs = qs.filter(staff__restaurant=restaurant)

            return qs

        # 3️⃣ Staff → only their own documents
        if role_name == "staff" and hasattr(user, "staff_profile"):
            return qs.filter(staff=user.staff_profile)

        # 4️⃣ Others → no access
        return qs.none()

        

class StaffViewSet(ProtectedModelViewSet):
    """
    CRUD for Staff profiles (auto-created when a user is assigned the staff role).

    Role-based access:
      - Superuser: can view/manage all staff across all hotels
      - Admin: can view/manage only staff within their assigned hotel
      - Staff: can only view their own profile
    """
    queryset = Staff.objects.all().select_related('user', 'hotel')
    serializer_class = StaffSerializer
    model_name = 'Staff'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = Staff.objects.all().select_related("user", "hotel", "restaurant")

        # 1️⃣ Superuser → all staff
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return Staff.objects.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → staff of their hotel OR restaurant
        if role_name == "admin":
            # Hotel admin
            hotel = Hotel.objects.filter(owner=user).first()
            if hotel:
                return qs.filter(hotel=hotel)

            # Restaurant admin
            restaurant = Restaurant.objects.filter(owner=user).first()
            if restaurant:
                return qs.filter(restaurant=restaurant)

            return Staff.objects.none()

        # 3️⃣ Staff → only their own profile
        if role_name == "staff":
            return qs.filter(user=user)

        # 4️⃣ Others → no access
        return Staff.objects.none()


    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        """
        Dashboard summary for staff management.
        Role-aware:
          - Superuser: all hotels
          - Admin: only their hotel
        """
        user = request.user
        hotel_id = request.query_params.get('hotel')

        staffs = self.get_queryset()

        # For superusers, allow optional ?hotel filter
        if user.is_superuser and hotel_id:
            staffs = staffs.filter(hotel_id=hotel_id)

        # For admins, always restrict to their own hotel
        elif hasattr(user, "role") and user.role.name.lower() == "admin":
            hotel = getattr(user, "hotel", None) or getattr(
                getattr(user, "staff_profile", None), "hotel", None
            )
            if not hotel:
                return Response({"error": "Admin not linked to any hotel."}, status=status.HTTP_400_BAD_REQUEST)
            staffs = staffs.filter(hotel=hotel)

        total_staff = staffs.count()
        active_staff = staffs.filter(status='active').count()

        # Calculate average performance (if property exists)
        avg_performance = 0.0
        if total_staff > 0:
            scores = [s.performance_score or 0 for s in staffs]
            avg_performance = round(sum(scores) / total_staff, 2)

        # Monthly payroll
        monthly_payroll = staffs.aggregate(total=Sum('monthly_salary'))['total'] or 0

        return Response({
            "total_staff": total_staff,
            "active_staff": active_staff,
            "avg_performance": f"{avg_performance}%",
            "monthly_payroll": float(monthly_payroll),
        })
        
        
class AttendanceViewSet(ProtectedModelViewSet):
    """
    Manage staff attendance records.
    """
    queryset = Attendance.objects.select_related('staff', 'staff__user').all()
    serializer_class = AttendanceSerializer
    model_name = 'Attendance'
    lookup_field = 'slug'
    
    @action(detail=False, methods=['post'], url_path='check-in')
    def check_in(self, request):
        user = request.user
        staff = getattr(user, 'staff_profile', None)
        if not staff:
            return Response({"error": "You are not assigned as staff."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        attendance, created = Attendance.objects.get_or_create(staff=staff, date=today)

        if attendance.check_in:
            return Response({"message": "Already checked in for today."}, status=status.HTTP_200_OK)

        attendance.check_in = timezone.localtime().time()  # ✅ FIXED
        attendance.status = 'present'
        attendance.save()

        return Response({
            "message": "Check-in successful.",
            "check_in_time": attendance.check_in,
            "date": today
        }, status=status.HTTP_200_OK)

    # ✅ Mark Check-Out
    @action(detail=False, methods=['post'], url_path='check-out')
    def check_out(self, request):
        user = request.user
        staff = getattr(user, 'staff_profile', None)
        if not staff:
            return Response({"error": "You are not assigned as staff."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        try:
            attendance = Attendance.objects.get(staff=staff, date=today)
        except Attendance.DoesNotExist:
            return Response({"error": "No check-in record found for today."}, status=status.HTTP_400_BAD_REQUEST)

        if attendance.check_out:
            return Response({"message": "Already checked out for today."}, status=status.HTTP_200_OK)

        attendance.check_out = timezone.localtime().time()  # ✅ FIXED
        attendance.save()

        duration = attendance.work_duration if hasattr(attendance, 'work_duration') else 0
        message = f"Checked out successfully. Worked for {duration} hours."

        return Response({
            "message": message,
            "check_out_time": attendance.check_out,
            "duration": duration
        }, status=status.HTTP_200_OK)

    # ✅ Auto Checkout (cron or manual)
    @action(detail=False, methods=['post'], url_path='auto-checkout')
    def auto_checkout(self, request):
        """Auto checkout staff if it's past 8 PM and they forgot to checkout."""
        now = timezone.localtime()
        cutoff = time(20, 0)  # 8:00 PM

        if now.time() < cutoff:
            return Response({"message": "Auto checkout can only run after 8 PM."}, status=status.HTTP_400_BAD_REQUEST)

        auto_checked = 0
        for attendance in Attendance.objects.filter(check_out__isnull=True, check_in__isnull=False, date=timezone.localdate()):
            attendance.check_out = cutoff
            attendance.save()
            auto_checked += 1

        return Response({"message": f"Auto checked out {auto_checked} staff at 8 PM."}, status=status.HTTP_200_OK)

    
from datetime import date

class PayrollViewSet(ProtectedModelViewSet):
    queryset = Payroll.objects.all().select_related('staff__user')
    serializer_class = PayrollSerializer
    model_name = 'Payroll'

    @action(detail=False, methods=['get'], url_path='monthly-summary')
    def monthly_summary(self, request):
        user = request.user
        hotel_id = request.query_params.get('hotel')

        staffs = Staff.objects.all()

        # 🔹 Role-based filtering
        if not user.is_superuser:
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                # Admin sees only their hotel’s staff
                staffs = staffs.filter(hotel__owner=user)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                # Staff sees only themselves
                staffs = staffs.filter(id=user.staff_profile.id)
            else:
                return Response(
                    {"error": "You are not associated with any hotel."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # 🔹 Optional hotel_id filter (only if allowed)
        if hotel_id:
            staffs = staffs.filter(hotel_id=hotel_id)

        # 🔹 Aggregation
        total_payroll = staffs.aggregate(total=Sum('monthly_salary'))['total'] or 0
        avg_salary = staffs.aggregate(avg=Avg('monthly_salary'))['avg'] or 0

        return Response({
            "total_payroll": float(total_payroll),
            "avg_salary": round(avg_salary, 2),
            "staff_count": staffs.count()
        })
        
        
    @action(detail=False, methods=['post'], url_path='generate-monthly')
    def generate_monthly_payroll(self, request):
        """
        Generate payroll for staff for the current month, with role-based filtering.
        - Superuser → all hotels
        - Admin → only their hotel’s staff
        - Staff → not allowed
        """
        user = request.user
        today = date.today()
        month, year = today.month, today.year
        created_count = 0

        # 🔹 Determine which staff to include
        staffs = Staff.objects.all()

        if not user.is_superuser:
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                staffs = staffs.filter(hotel__owner=user)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                return Response(
                    {"error": "You are not authorized to generate payrolls."},
                    status=status.HTTP_403_FORBIDDEN
                )
            else:
                return Response(
                    {"error": "You are not associated with any hotel."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # 🔹 Generate payrolls safely
        with transaction.atomic():
            for staff in staffs:
                exists = Payroll.objects.filter(staff=staff, month=month, year=year).exists()
                if not exists:
                    Payroll.objects.create(
                        staff=staff,
                        salary_type='attendance_based',
                        base_salary=staff.monthly_salary,
                        month=month,
                        year=year
                    )
                    created_count += 1

        return Response(
            {"message": f"✅ Payroll generated for {created_count} staff members for {month}/{year}."},
            status=status.HTTP_201_CREATED
        )
    

class LeaveViewSet(ProtectedModelViewSet):
    queryset = Leave.objects.select_related('staff', 'staff__user', 'approved_by').all()
    serializer_class = LeaveSerializer
    model_name = 'Leave'
    lookup_field = 'slug'
    
    def perform_create(self, serializer):
        return serializer.save()

    # ✅ Approve leave
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        leave = self.get_object()
        if leave.status != 'pending':
            return Response({"error": "Leave already processed."}, status=status.HTTP_400_BAD_REQUEST)
        leave.status = 'approved'
        leave.approved_by = request.user
        leave.save(update_fields=['status', 'approved_by'])
        return Response({"message": "Leave approved successfully."})

    # ✅ Reject leave
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        leave = self.get_object()
        if leave.status != 'pending':
            return Response({"error": "Leave already processed."}, status=status.HTTP_400_BAD_REQUEST)
        leave.status = 'rejected'
        leave.approved_by = request.user
        leave.save(update_fields=['status', 'approved_by'])
        return Response({"message": "Leave rejected."})



class StaffDashboardViewSet(ProtectedModelViewSet):
    """
    Staff Dashboard Overview API
    """
    queryset = Staff.objects.select_related('user', 'hotel').all()
    serializer_class = StaffDashboardOverviewSerializer
    model_name = 'StaffDashboard'
    lookup_field = 'slug'

    @action(detail=False, methods=['get'], url_path='overview')
    def overview(self, request):
        user = request.user

        # ==============================
        # 🔐 SAME QUERYSET LOGIC (JAISA STAFFVIEWSET)
        # ==============================
        staffs = self.get_queryset()

        if user.is_superuser:
            pass

        elif hasattr(user, "role") and user.role and user.role.name.lower() == "admin":
            hotel = getattr(user, "hotel", None) or getattr(
                getattr(user, "staff_profile", None), "hotel", None
            )
            if not hotel:
                return Response(
                    {"error": "Admin not linked to any hotel."},
                    status=status.HTTP_403_FORBIDDEN
                )
            staffs = staffs.filter(hotel=hotel)

        elif hasattr(user, "staff_profile"):
            staffs = staffs.filter(id=user.staff_profile.id)

        else:
            return Response(
                {"error": "You are not authorized."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Optional staff filter (?staff=slug)
        staff_slug = request.query_params.get("staff")
        if staff_slug:
            staffs = staffs.filter(slug=staff_slug)

        staff = staffs.first()
        if not staff:
            return Response(
                {"error": "Staff not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ==============================
        # 📊 DASHBOARD CALCULATIONS
        # ==============================

        # 🔹 Assigned / Pending Tasks (future ready)
        assigned_tasks = 0
        pending_work = 0

        # 🔹 Attendance → Daily Activity %
        total_days = Attendance.objects.filter(staff=staff).count()
        present_days = Attendance.objects.filter(
            staff=staff,
            status='present'
        ).count()

        daily_activity = round(
            (present_days / total_days) * 100, 2
        ) if total_days > 0 else 0

        # 🔹 Notifications (future ready)
        notifications_count = 0
        recent_notifications = []

        # ==============================
        # 📦 RESPONSE (FRONTEND READY)
        # ==============================
        return Response({
            "user": {
                "name": staff.user.full_name,
                "email": staff.user.email
            },
            "cards": {
                "assigned_tasks": assigned_tasks,
                "pending_work": pending_work,
                "daily_activity": daily_activity,
                "notifications": notifications_count
            },
            "recent_notifications": recent_notifications
        }, status=status.HTTP_200_OK)
