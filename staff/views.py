from MBP.views import ProtectedModelViewSet
from .models import Staff, Attendance, Payroll
from .serializers import StaffSerializer, AttendanceSerializer, PayrollSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, F, Avg, Sum


class StaffViewSet(ProtectedModelViewSet):
    """
    CRUD for Staff profiles (auto-created when user assigned staff role).
    """
    queryset = Staff.objects.all().select_related('user')
    serializer_class = StaffSerializer
    model_name = 'Staff'

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
    queryset = Attendance.objects.all().select_related('staff')
    serializer_class = AttendanceSerializer
    model_name = 'Attendance'
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class PayrollViewSet(ProtectedModelViewSet):
    """
    View total payrolls grouped by month or by hotel.
    """
    model_name = 'staff-payroll'
    serializer_class = PayrollSerializer
    

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