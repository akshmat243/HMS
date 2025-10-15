# staff/admin.py
from django.contrib import admin
from .models import Staff, Attendance, Payroll, Leave
from django.utils.html import format_html
from decimal import Decimal


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'hotel', 'designation', 'department',
        'status', 'joining_date', 'get_monthly_salary',
        'performance_score_display',
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'designation', 'department')
    list_filter = ('status', 'department', 'hotel')
    readonly_fields = ('slug', 'created_at', 'updated_at', 'performance_score_display')

    def get_monthly_salary(self, obj):
        return f"₹{obj.monthly_salary:.2f}"
    get_monthly_salary.short_description = "Base Salary"

    def performance_score_display(self, obj):
        return f"{obj.performance_score}%"
    performance_score_display.short_description = "Performance Score"


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('staff', 'date', 'status', 'check_in', 'check_out', 'remarks')
    list_filter = ('status', 'date')
    search_fields = ('staff__user__full_name',)
    readonly_fields = ('id',)
    ordering = ('-date',)


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = (
        'staff', 'salary_type', 'month', 'year',
        'base_salary', 'total_salary', 'get_status_icon', 'created_at'
    )
    list_filter = ('salary_type', 'month', 'year')
    search_fields = ('staff__user__username',)
    readonly_fields = ('slug', 'total_salary', 'created_at')

    actions = ['recalculate_selected_payrolls']

    def get_status_icon(self, obj):
        color = "green" if obj.salary_type == "monthly" else "blue"
        return format_html(
            f'<span style="color:{color}; font-weight:bold;">{obj.salary_type.title()}</span>'
        )
    get_status_icon.short_description = "Type"

    @admin.action(description="Recalculate selected payrolls")
    def recalculate_selected_payrolls(self, request, queryset):
        for payroll in queryset:
            payroll.total_salary = payroll.calculate_salary()
            payroll.save()
        self.message_user(request, f"Recalculated {queryset.count()} payroll(s).")

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ('staff', 'start_date', 'end_date', 'status', 'approved_by', 'created_at')
    list_filter = ('status', 'start_date', 'end_date')
    search_fields = ('staff__user__full_name', 'reason', 'approved_by__full_name')
    readonly_fields = ('slug', 'created_at', 'approved_by')

    actions = ['approve_leaves', 'reject_leaves']

    @admin.action(description="Approve selected leaves")
    def approve_leaves(self, request, queryset):
        updated = queryset.update(status='approved', approved_by=request.user)
        self.message_user(request, f"Approved {updated} leave(s).")

    @admin.action(description="Reject selected leaves")
    def reject_leaves(self, request, queryset):
        updated = queryset.update(status='rejected', approved_by=request.user)
        self.message_user(request, f"Rejected {updated} leave(s).")