from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Payment
from Hotel.models import Booking  # Import your Booking model
from django.contrib.contenttypes.models import ContentType

@receiver(post_save, sender=Payment)
def update_booking_status_on_payment(sender, instance, **kwargs):
    """
    Automatically confirm booking if invoice is partially or fully paid.
    """
    invoice = instance.invoice

    # Check if the invoice is linked to a Booking
    if invoice.content_type.model == 'Booking':
        try:
            booking = Booking.objects.get(id=invoice.object_id)
        except Booking.DoesNotExist:
            return

        # ✅ Update booking status based on invoice payment status
        if invoice.status in ['partial', 'paid']:
            if booking.status != 'confirmed':
                booking.status = 'confirmed'
                booking.save(update_fields=['status'])
        else:
            if booking.status != 'pending':
                booking.status = 'pending'
                booking.save(update_fields=['status'])
