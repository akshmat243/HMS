from django.db.models.signals import post_save
from django.dispatch import receiver
from Billing.models import Invoice
from .models import PurchaseOrder

@receiver(post_save, sender=Invoice)
def update_purchase_order_payment_status(sender, instance, **kwargs):
    """Sync invoice payment status with purchase order."""
    if instance.content_type.model == 'purchaseorder':
        try:
            order = instance.content_type.get_object_for_this_type(id=instance.object_id)
            order.payment_status = instance.status
            order.save()
        except PurchaseOrder.DoesNotExist:
            pass
