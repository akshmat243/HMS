from MBP.views import ProtectedModelViewSet
from .models import Staff, Attendance, Payroll, Leave
from .serializers import StaffSerializer, AttendanceSerializer, PayrollSerializer, LeaveSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import time
from django.utils import timezone
from rest_framework import status
from django.db.models import Count, Q, F, Avg, Sum
from django.db import transaction


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
        """Filter queryset based on user role."""
        user = self.request.user

        # 1️⃣ Superuser → All staff
        if user.is_superuser:
            return Staff.objects.all()

        # 2️⃣ Admin → Only staff in their hotel
        if hasattr(user, "role") and user.role.name.lower() == "admin":
            hotel = getattr(user, "hotel", None) or getattr(
                getattr(user, "staff_profile", None), "hotel", None
            )
            if hotel:
                return Staff.objects.filter(hotel=hotel)
            return Staff.objects.none()

        # 3️⃣ Staff → Only their own record
        if hasattr(user, "role") and user.role.name.lower() == "staff":
            return Staff.objects.filter(user=user)

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