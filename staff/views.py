from MBP.views import ProtectedModelViewSet
from .models import Staff, Attendance, Payroll, Leave
from .serializers import StaffSerializer, AttendanceSerializer, PayrollSerializer, LeaveSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import time
from django.utils import timezone
from rest_framework import status
from django.db.models import Count, Q, F, Avg, Sum


class StaffViewSet(ProtectedModelViewSet):
    """
    CRUD for Staff profiles (auto-created when user assigned staff role).
    """
    queryset = Staff.objects.all().select_related('user')
    serializer_class = StaffSerializer
    model_name = 'Staff'
    lookup_field = 'slug'

    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        """
        Returns key staff statistics for dashboard.
        """
        hotel_id = request.query_params.get('hotel')
        staffs = Staff.objects.all()
        if hotel_id:
            staffs = staffs.filter(hotel_id=hotel_id)

        total_staff = staffs.count()
        active_staff = staffs.filter(status='active').count()

        # Average performance (based on dynamic property)
        avg_performance = 0
        if total_staff > 0:
            scores = [s.performance_score for s in staffs]
            avg_performance = round(sum(scores) / len(scores), 2)

        # Monthly payroll sum
        monthly_payroll = staffs.aggregate(total=Sum('monthly_salary'))['total'] or 0

        return Response({
            "total_staff": total_staff,
            "active_staff": active_staff,
            "avg_performance": f"{avg_performance}%",
            "monthly_payroll": float(monthly_payroll)
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

        attendance.check_in = timezone.localtime().time()
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

        attendance.check_out = timezone.localtime().time()
        attendance.save()

        duration = attendance.work_duration or 0
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


class PayrollViewSet(ProtectedModelViewSet):
    """
    View total payrolls grouped by month or by hotel.
    """
    model_name = 'staff-payroll'
    serializer_class = PayrollSerializer
    lookup_field = 'slug'
    

    @action(detail=False, methods=['get'], url_path='monthly-summary')
    def monthly_summary(self, request):
        hotel_id = request.query_params.get('hotel')
        staffs = Staff.objects.all()
        if hotel_id:
            staffs = staffs.filter(hotel_id=hotel_id)

        total_payroll = staffs.aggregate(total=Sum('monthly_salary'))['total'] or 0
        avg_salary = staffs.aggregate(avg=Avg('monthly_salary'))['avg'] or 0

        return Response({
            "total_payroll": float(total_payroll),
            "avg_salary": round(avg_salary, 2),
            "staff_count": staffs.count()
        })

from datetime import date

class PayrollViewSet(ProtectedModelViewSet):
    queryset = Payroll.objects.all().select_related('staff__user')
    serializer_class = PayrollSerializer
    model_name = 'Payroll'

    @action(detail=False, methods=['post'], url_path='generate-monthly')
    def generate_monthly_payroll(self, request):
        """
        Generate payroll for all staff for the current month if not already exists.
        """
        today = date.today()
        month, year = today.month, today.year
        created_count = 0

        for staff in Staff.objects.all():
            if not Payroll.objects.filter(staff=staff, month=month, year=year).exists():
                Payroll.objects.create(
                    staff=staff,
                    salary_type='attendance_based',
                    base_salary=staff.monthly_salary,
                    month=month,
                    year=year
                )
                created_count += 1

        return Response({"message": f"Payroll generated for {created_count} staff members."})
    

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