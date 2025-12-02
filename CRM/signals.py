from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import F

# App Models Imports
from Billing.models import Invoice
from Hotel.models import Guest
from .models import Customer
from MBP.models import Role
from accounts.models import Profile

User = get_user_model()

# ==========================================
# 1. LOYALTY POINTS + STATUS UPDATE (Invoice Paid)
# ==========================================
@receiver(post_save, sender=Invoice)
def update_customer_stats(sender, instance, created, **kwargs):
    """
    Jab Invoice 'paid' ho:
    1. Customer ke Loyalty Points recalculate karo.
    2. Last Visit date update karo (aaj ki date).
    3. Status ko wapas 'Active' set karo.
    """
    if instance.status == 'paid' and instance.issued_to and instance.issued_to.email:
        email = instance.issued_to.email
        
        # Customer dhoondo (Invoice wale User ki email se)
        # Note: Agar multiple hotels hain, to ideally Invoice mein Hotel field honi chahiye filter ke liye.
        # Abhi ke liye hum email se match kar rahe hain.
        customers = Customer.objects.filter(email=email)
        
        for customer in customers:
            # A. Loyalty Points Calculation (Model method call)
            customer.update_loyalty_points()
            
            # B. Status & Last Visit Update
            # Hum direct update use kar rahe hain taaki save() method ka loop na chale
            Customer.objects.filter(id=customer.id).update(
                last_visit=timezone.now(),
                status='active'  # 👈 Customer Inactive tha to Active ho jayega
            )

# ==========================================
# 2. AUTO USER CREATION (Customer -> User)
# ==========================================
@receiver(post_save, sender=Customer)
def create_user_for_customer(sender, instance, created, **kwargs):
    """
    Jab naya CRM Customer bane, to uska User Account (Login) bhi bana do.
    """
    if created:
        email = instance.email
        phone = instance.phone

        # Duplicate Check
        if User.objects.filter(email=email).exists(): return
        if User.objects.filter(phone=phone).exists(): return

        try:
            # Role assign karo
            customer_role, _ = Role.objects.get_or_create(
                name="Customer",
                defaults={'description': 'Auto-generated role for CRM Customers'}
            )

            # User create karo
            new_user = User.objects.create_user(
                email=email,
                phone=phone,
                full_name=instance.name,
                role=customer_role,
                is_active=True,         # Login allow karne ke liye
                is_email_verified=True, 
                is_phone_verified=True
            )

            # Profile create karo (Address/Image ke saath)
            Profile.objects.create(
                user=new_user,
                phone=phone,
                address=f"{instance.address}, {instance.city}, {instance.country}".strip(', '),
                profile_picture=instance.image,
                gender='other',  # Default
                dob='2000-01-01' # Default
            )
            print(f"SUCCESS: Created User for Customer: {instance.name}")

        except Exception as e:
            print(f"ERROR creating user for customer {instance.name}: {str(e)}")

# ==========================================
# 3. GUEST TO CUSTOMER SYNC (Guest -> Customer)
# ==========================================
@receiver(post_save, sender=Guest)
def sync_guest_to_crm(sender, instance, created, **kwargs):
    """
    Jab Hotel mein Guest add ho, to use CRM Customer bana do.
    Ensure karo ki wo usi Hotel se link ho jahan Booking hui hai.
    """
    if created and instance.email:
        # Step A: Guest kis hotel ka hai? (Guest -> Booking -> Hotel)
        booking = instance.booking
        hotel = booking.hotel if booking else None

        # Step B: Check karo agar Customer pehle se hai (Same Email + Same Hotel)
        if not Customer.objects.filter(email=instance.email, hotel=hotel).exists():
            try:
                full_name = f"{instance.first_name} {instance.last_name or ''}".strip()
                
                Customer.objects.create(
                    hotel=hotel,         # 👈 Isolation ke liye zaroori hai
                    name=full_name,
                    email=instance.email,
                    phone=instance.phone or "",
                    address=instance.address or "",
                    customer_type='regular',
                    status='active',     # Abhi aaya hai to Active hi hoga
                    preferences=f"ID Proof: {instance.id_proof_type or 'N/A'}",
                )
                print(f"SYNC SUCCESS: Guest '{full_name}' added to CRM for hotel {hotel.name if hotel else 'Unknown'}.")
            except Exception as e:
                print(f"SYNC ERROR: Could not add guest to CRM: {str(e)}")