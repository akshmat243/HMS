from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from .models import User  # adjust import based on your structure

from django.dispatch import Signal

user_created_with_password = Signal()



@receiver(user_created_with_password)
def send_credentials_and_verification(sender, user, raw_password, **kwargs):
    verification_link = (
        f"http://192.168.1.24:8000/api/verify-email-reset-password/{user.slug}/"
    )

    send_mail(
        subject="Verify your email & login credentials",
        message=f"""
Hello {user.full_name},

Your staff account has been created.

Login Email: {user.email}
Temporary Password: {raw_password}

Please verify your email and reset your password using the link below:
{verification_link}

Regards,
Hotel Management System
""",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


