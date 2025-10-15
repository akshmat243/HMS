import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal
from Hotel.models import Hotel
from datetime import datetime

User = settings.AUTH_USER_MODEL


class Staff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True, related_name='staff')
    slug = models.SlugField(unique=True, blank=True)

    designation = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    profile_image = models.ImageField(upload_to='staff_profiles/', blank=True, null=True)

    joining_date = models.DateField(default=timezone.now)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    # 🕒 Shift details
    shift_start = models.TimeField(blank=True, null=True)
    shift_end = models.TimeField(blank=True, null=True)

    # 💰 Salary
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave')
    ], default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.user.full_name or str(self.user.id))
            slug = base_slug
            num = 1
            while Staff.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{num}"
                num += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.full_name} - {self.designation or 'Staff'}"
    
    @property
    def performance_score(self):
        """
        Dynamic performance calculation based on attendance rate.
        Example: (Days Present / Total Days) * 100
        """
        total_days = self.attendance_records.count()
        if total_days == 0:
            return 0
        present_days = self.attendance_records.filter(status='present').count()
        score = (present_days / total_days) * 100
        return round(score, 2)


class Attendance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    check_in = models.TimeField(blank=True, null=True)
    check_out = models.TimeField(blank=True, null=True)
    work_duration = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=10, choices=[
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('leave', 'Leave'),
    ], default='absent')
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('staff', 'date')

    def save(self, *args, **kwargs):
        if self.check_in and self.check_out:
            in_dt = datetime.combine(self.date, self.check_in)
            out_dt = datetime.combine(self.date, self.check_out)
            diff = out_dt - in_dt
            self.work_duration = round(diff.total_seconds() / 3600, 2)  # hours
            # mark present if >= 8 hrs
            if self.work_duration >= 8:
                self.status = 'present'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff.user.full_name} - {self.date} ({self.status})"


class Payroll(models.Model):
    SALARY_TYPE_CHOICES = [
        ('monthly', 'Monthly'),
        ('attendance_based', 'Attendance Based'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='payrolls')
    salary_type = models.CharField(max_length=30, choices=SALARY_TYPE_CHOICES, default='monthly')
    base_salary = models.DecimalField(max_digits=10, decimal_places=2)
    total_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    month = models.PositiveIntegerField()
    year = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def calculate_salary(self):
        from staff.models import Attendance  # local import to avoid circular reference

        if self.salary_type == 'attendance_based':
            total_days = Attendance.objects.filter(
                staff=self.staff,
                date__month=self.month,
                date__year=self.year,
                status='present'
            ).count()

            # Assuming 30-day month for simplicity
            per_day = Decimal(self.base_salary) / Decimal(30)
            return round(per_day * total_days, 2)
        return self.base_salary
    
    @property
    def current_salary(self):
        """
        Returns the latest total salary from Payroll for this staff.
        """
        latest_payroll = self.payrolls.order_by('-year', '-month').first()
        if latest_payroll:
            return latest_payroll.total_salary
        return self.monthly_salary 

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug:
            self.slug = slugify(f"payroll-{self.staff.user.username}-{uuid.uuid4().hex[:6]}")
        self.total_salary = self.calculate_salary()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff.user.get_full_name()} - {self.month}/{self.year}"
    
class Leave(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='leaves')
    slug = models.SlugField(unique=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.staff.user.full_name}-{self.start_date}-{self.end_date}")
            counter = 1
            new_slug = base_slug
            while Leave.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff.user.full_name} | {self.start_date} → {self.end_date} ({self.status})"
