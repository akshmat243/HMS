from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from accounts.models import User, UserModule
from Hotel.models import Hotel
from Restaurant.models import Restaurant


@receiver(post_save, sender=User)
def create_admin_business_units(sender, instance, created, **kwargs):
    """
    Create Hotel / Restaurant automatically
    based on admin-selected modules.
    """
    if not created:
        return

    # Only for admin role
    if not instance.role or instance.role.name.lower() != "admin":
        return

    # Fetch active modules
    modules = instance.modules.filter(is_active=True).values_list("module", flat=True)

    # 🏨 Create Hotel if module selected
    if "hotel" in modules:
        Hotel.objects.get_or_create(
            owner=instance,
            defaults={
                "name": f"{instance.full_name}'s Hotel"
            }
        )

    # 🍽 Create Restaurant if module selected
    if "restaurant" in modules:
        Restaurant.objects.get_or_create(
            owner=instance,
            defaults={
                "name": f"{instance.full_name}'s Restaurant",
                "rating": 5.0
            }
        )

@receiver(post_delete, sender=Hotel)
def disable_hotel_module(sender, instance, **kwargs):
    UserModule.objects.filter(
        user=instance.owner,
        module="hotel"
    ).update(is_active=False)
