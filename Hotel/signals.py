from django.db.models.signals import post_save
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

