from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from django.dispatch import Signal

user_created_with_password = Signal()


@receiver(user_created_with_password)
def send_credentials_and_verification(sender, user, raw_password, **kwargs):
    verification_link = (
        f"http://localhost:8080/verify-email-reset-password/{user.slug}/"
    )

    subject = "Verify your email & login credentials"

    # Plain-text fallback (important)
    text_message = f"""
Hello {user.full_name},

Your account has been created.

Login Email: {user.email}
Temporary Password: {raw_password}

Please verify your email and reset your password using the link below:
{verification_link}

Regards,
Hotel Management System
"""

    # ✅ HTML email with button
    html_message = f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    .btn {{
      display: inline-block;
      padding: 12px 20px;
      font-size: 16px;
      color: #ffffff !important;
      background-color: #2563eb;
      text-decoration: none;
      border-radius: 6px;
      font-weight: bold;
    }}
    .container {{
      font-family: Arial, sans-serif;
      color: #333333;
      line-height: 1.6;
    }}
    .footer {{
      margin-top: 30px;
      font-size: 13px;
      color: #777777;
    }}
  </style>
</head>
<body>
  <div class="container">
    <p>Hello <strong>{user.full_name}</strong>,</p>

    <p>Your account has been created.</p>

    <p>
      <strong>Login Email:</strong> {user.email}<br>
      <strong>Temporary Password:</strong> {raw_password}
    </p>

    <p>Please verify your email and reset your password by clicking the button below:</p>

    <p>
      <a href="{verification_link}" class="btn">
        Verify Email & Reset Password
      </a>
    </p>

    <p class="footer">
      If you did not request this account, please ignore this email.<br>
      <br>
      Regards,<br>
      <strong>Hotel Management System</strong>
    </p>
  </div>
</body>
</html>
"""

    send_mail(
        subject=subject,
        message=text_message,        # fallback for non-HTML clients
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,   # THIS renders the button
        fail_silently=False,
    )
    

from django.dispatch import Signal, receiver
from django.conf import settings
from django.core.mail import send_mail

# custom signal
user_registered = Signal()  # provides: user

@receiver(user_registered)
def send_verification_email(sender, user, **kwargs):
    verification_link = (
        f"http://localhost:8080/verify-email/{user.slug}/"
    )

    subject = "Verify your email address"

    text_message = f"""
Hello {user.full_name},

Thank you for registering.

Please verify your email by clicking the link below:
{verification_link}

If you did not create this account, please ignore this email.

Regards,
Hotel Management System
"""

    html_message = f"""
    <html>
      <body style="font-family: Arial, sans-serif;">
        <p>Hello <strong>{user.full_name}</strong>,</p>

        <p>Thank you for registering.</p>

        <p>Please verify your email by clicking the button below:</p>

        <p>
          <a href="{verification_link}"
             style="
               background-color:#2563eb;
               color:white;
               padding:12px 20px;
               text-decoration:none;
               border-radius:6px;
               font-weight:bold;
             ">
            Verify Email
          </a>
        </p>

        <p>If you did not create this account, please ignore this email.</p>

        <p>Regards,<br><strong>Hotel Management System</strong></p>
      </body>
    </html>
    """

    send_mail(
        subject=subject,
        message=text_message,        # fallback
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )
