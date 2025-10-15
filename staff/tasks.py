from celery import shared_task
from django.utils import timezone
from datetime import time
from .models import Attendance

@shared_task
def auto_checkout_and_absent_marking():
    """
    - Auto check-out all staff who checked in but didn’t check out by 8 PM.
    - Mark staff absent if they never checked in by 8 PM.
    """
    now = timezone.localtime()
    today = timezone.localdate()
    cutoff = time(20, 0)  # 8 PM

    if now.time() < cutoff:
        return "Not 8 PM yet — skipping automation."

    # ✅ Auto checkout all checked-in staff
    auto_checked = 0
    for attendance in Attendance.objects.filter(date=today, check_in__isnull=False, check_out__isnull=True):
        attendance.check_out = cutoff
        attendance.save()
        auto_checked += 1

    # ✅ Mark absent those who didn’t check in at all
    from staff.models import Staff
    all_staff = Staff.objects.all()
    absent_marked = 0
    for staff in all_staff:
        if not Attendance.objects.filter(staff=staff, date=today).exists():
            Attendance.objects.create(
                staff=staff,
                date=today,
                status='absent',
                remarks='Auto-marked absent (no check-in by 8 PM)'
            )
            absent_marked += 1

    return f"Auto checkout: {auto_checked}, Marked absent: {absent_marked}"
