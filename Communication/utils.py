from django.core.mail import send_mail

def send_newsletter(email):
    subject = "You're now subscribed to our Newsletter "
    message = (
        "Thank you for subscribing!\n\n"
        "You'll now receive exclusive offers, updates, and travel inspirations.\n\n"
    )

    send_mail(
        subject,
        message,
        None,          # DEFAULT_FROM_EMAIL use hoga
        [email],
        fail_silently=False,
    )
