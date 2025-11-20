from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from .models import User  # adjust import based on your structure

@receiver(post_save, sender=User)
def send_verification_email_on_create(sender, instance, created, **kwargs):
    """Send email verification link whenever a user is created."""
    if created:
        # # ✅ Generate OTP for phone
        # otp = str(random.randint(100000, 999999))
        
        # # ✅ Store OTP in cache for 5 min
        # cache.set(f"otp_{user.phone}", otp, timeout=300)
        # print(f"DEBUG: OTP for {user.phone} is {otp}")  # Replace with Twilio SMS later
        
        
        verification_link = f"http://127.0.0.1:8000/api/verify-email/{instance.slug}/"

        subject = "Verify your email"
        message = (
            f"Hello {instance.full_name},\n\n"
            f"Click here to verify your email:\n{verification_link}\n\n"
            f"This link will expire soon. If you did not request this, ignore the message."
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
            fail_silently=False,
        )
