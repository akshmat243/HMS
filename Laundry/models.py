import uuid
from django.db import models
from django.utils.text import slugify
from Hotel.models import Hotel, Room
from django.contrib.auth import get_user_model

User = get_user_model()


class LaundryService(models.Model):
    RATE_TYPE_CHOICES = [
        ('per_kg', 'Per Kilogram'),
        ('per_piece', 'Per Piece'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    rate = models.DecimalField(max_digits=8, decimal_places=2)
    rate_type = models.CharField(max_length=20, choices=RATE_TYPE_CHOICES)
    estimated_time = models.DurationField(help_text="Estimated completion time")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            new_slug = base_slug
            counter = 1
            while LaundryService.objects.filter(slug=new_slug).exists():
                new_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = new_slug
        super().save(*args, **kwargs)


class LaundryOrder(models.Model):
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('washing', 'Washing'),
        ('ready', 'Ready'),
        ('delivered', 'Delivered'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='laundry_orders')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, related_name='laundry_orders')
    service = models.ForeignKey(LaundryService, on_delete=models.SET_NULL, null=True, related_name='laundry_orders')
    items_description = models.TextField(help_text="Describe the clothes/items")
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="In KG (if per kg)")
    quantity = models.PositiveIntegerField(null=True, blank=True, help_text="If per piece")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Laundry Order #{self.id} - Room {self.room.room_number if self.room else 'N/A'}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            room_number = self.room.room_number if self.room else 'room'
            base = f"{room_number}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)