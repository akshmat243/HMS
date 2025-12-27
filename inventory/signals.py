from django.db.models.signals import post_save
from django.dispatch import receiver
from Billing.models import Invoice
from .models import PurchaseOrder, Supplier
from MBP.models import Role
from django.contrib.auth import get_user_model
from accounts.signals import user_created_with_password
User = get_user_model()

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

@receiver(post_save, sender=Supplier)
def create_supplier_user(sender, instance, created, **kwargs):
    # Sirf tab jab naya supplier bane aur user link na ho
    if created and not instance.user:
        try:
            # 1. Vendor Role fetch karein
            vendor_role = Role.objects.filter(name__iexact='vendor').first()
            
            # 2. Credential set karein
            user_email = instance.email
            raw_password = "Welcome@123" # Temporary password
            
            if not user_email:
                # Agar email nahi hai to creation skip ya error handling
                return

            if not User.objects.filter(email=user_email).exists():
                # 3. User Create karein (is_email_verified False hi rahega default se)
                new_user = User.objects.create(
                    email=user_email,
                    full_name=instance.name,
                    phone=instance.phone,
                    role=vendor_role,
                    is_active=True,  # Login allow karne ke liye active zaroori hai
                    created_by=instance.admin,
                    force_password_change = True
                )
                new_user.set_password(raw_password)
                new_user.save()

                # 4. Supplier ko user se link karein
                Supplier.objects.filter(pk=instance.pk).update(user=new_user)

                # 5. 🔥 Aapka Custom Signal Trigger karein
                # Ye accounts/signals.py ko message bhejega email bhejne ke liye
                user_created_with_password.send(
                    sender=User, 
                    user=new_user, 
                    raw_password=raw_password
                )
                
        except Exception as e:
            print(f"Error in supplier signal: {e}")