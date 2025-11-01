from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Hotel
from accounts.models import User  # adjust path based on your structure

@receiver(post_save, sender=User)
def create_admin_hotel(sender, instance, created, **kwargs):
    if created and getattr(instance, 'role', None) and instance.role.name == 'Admin':
        Hotel.objects.get_or_create(
            owner=instance,
            defaults={'name': f"{instance.full_name}'s Hotel"}
        )
