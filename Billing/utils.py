from django.contrib.contenttypes.models import ContentType
from .models import Invoice, InvoiceItem, Payment

def generate_invoice(instance, user, items):
    """
    Create invoice for ANY object (booking, order, service, etc.)
    """
    content_type = ContentType.objects.get_for_model(instance.__class__)

    invoice = Invoice.objects.create(
        content_type=content_type,
        object_id=instance.id,
        issued_to=user,
        total_amount=sum(item['amount'] for item in items),
    )

    # Create invoice items
    for item in items:
        InvoiceItem.objects.create(
            invoice=invoice,
            description=item['description'],
            quantity=item.get('quantity', 1),
            unit_price=item['unit_price']
        )

    return invoice


def create_payment(invoice, amount, method="cash", reference=""):
    """
    Create payment and automatically update invoice status.
    """
    payment = Payment.objects.create(
        invoice=invoice,
        amount_paid=amount,
        method=method,
        reference=reference
    )
    return payment
