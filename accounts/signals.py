from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from .models import User  # adjust import based on your structure


@receiver(post_save, sender=User)
def send_verification_email_on_create(sender, instance, created, **kwargs):
    """
    Send email ONLY when user is created.
    Includes:
    - temporary password
    - email verification link
    """
    if not created:
        return

    # Temporary password (set in serializer)
    raw_password = getattr(instance, "_raw_password", None)
    print(raw_password)

    verification_link = (
        f"http://192.168.1.24:8000/api/verify-email-reset-password/"
        f"{instance.slug}/"
    )

    subject = "Verify your email & login credentials"

    message = f"""
Hello {instance.full_name},

Your staff account has been created.

Login Email: {instance.email}
Temporary Password: {raw_password if raw_password else 'Set during login'}

Please verify your email and reset your password using the link below:
{verification_link}

If you did not request this account, please ignore this email.

Regards,
Hotel Management System
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[instance.email],
        fail_silently=False,
    )

