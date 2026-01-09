from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import RestaurantOrder, Restaurant
from accounts.models import User, UserModule
from Billing.models import Invoice, InvoiceItem

@receiver(post_save, sender=RestaurantOrder)
def manage_restaurant_invoice(sender, instance, created, **kwargs):
    """
    Jab bhi RestaurantOrder save hoga, ye signal Invoice create ya update karega.
    """
    # Agar order mein value hai tabhi invoice banao
    if instance.grand_total > 0:
        content_type = ContentType.objects.get_for_model(RestaurantOrder)
        
        # 1. Invoice dhoondo ya naya banao
        # Hum instance.hotel.owner ko issued_to bana rahe hain kyunki signal me 'request.user' nahi hota
        invoice, created = Invoice.objects.get_or_create(
            content_type=content_type,
            object_id=instance.id,
            defaults={
                "customer_name": instance.guest_name,
                "total_amount": instance.grand_total,
                "status": "unpaid",
                "issued_to": instance.hotel.owner 
            }
        )

        # 2. Agar invoice purana hai (Update case), to nayi values set karo
        if not created:
            invoice.total_amount = instance.grand_total
            invoice.customer_name = instance.guest_name
            invoice.save(update_fields=['total_amount', 'customer_name'])
        
        # 3. Invoice Items Sync karo (Purane delete -> Naye create)
        # Ye isliye zaruri hai taki agar menu item change hua ho to invoice me bhi dikhe
        invoice.items.all().delete()
        
        restaurant_items = instance.order_items.all()
        for item in restaurant_items:
            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"{item.menu_item.name}", # Menu item ka naam
                quantity=item.quantity,
                unit_price=item.price
            )
            

@receiver(post_delete, sender=Restaurant)
def disable_restaurant_module(sender, instance, **kwargs):
    UserModule.objects.filter(
        user=instance.owner,
        module="restaurant"
    ).update(is_active=False)
