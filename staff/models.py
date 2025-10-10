import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Staff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    hotel = models.ForeignKey('Hotel.Hotel', on_delete=models.CASCADE, null=True, blank=True, related_name='staff')
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
        return f"{self.user.get_full_name()} - {self.designation or 'Staff'}"
    
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
    status = models.CharField(max_length=10, choices=[
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('leave', 'Leave'),
    ], default='absent')
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('staff', 'date')

    def __str__(self):
        return f"{self.staff.user.username} - {self.date} ({self.status})"
