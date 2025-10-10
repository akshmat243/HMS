from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Staff, Attendance
from django.utils import timezone
from django.contrib.auth import get_user_model
User = get_user_model()


@receiver(post_save, sender=User)
def create_staff_profile(sender, instance, created, **kwargs):
    """
    Automatically create a Staff profile when a user is assigned a 'staff' role.
    """
    if created and getattr(instance, "role", None) == "staff":
        staff = Staff.objects.create(user=instance)
        Attendance.objects.get_or_create(staff=staff, date=timezone.now())
    elif not created and getattr(instance, "role", None) == "staff":
        Staff.objects.get_or_create(user=instance)
