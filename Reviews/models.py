import uuid
from django.db import models
from django.contrib.auth import get_user_model
from Hotel.models import Hotel
from Restaurant.models import MenuItem

User = get_user_model()


class HotelReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='hotel_reviews')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(default=5)  # 1 to 5
    comment = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hotel.name} ({self.rating}⭐)"


class RestaurantReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='restaurant_reviews')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, related_name='reviews')
    rating = models.PositiveIntegerField(default=5)
    comment = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.menu_item.name if self.menu_item else 'N/A'} ({self.rating}⭐)"


class ServiceReview(models.Model):
    SERVICE_TYPE_CHOICES = [
        ('laundry', 'Laundry'),
        ('room_service', 'Room Service'),
        ('spa', 'Spa'),
        ('others', 'Others'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='service_reviews')
    service_type = models.CharField(max_length=50, choices=SERVICE_TYPE_CHOICES)
    reference_id = models.UUIDField(help_text="ID of the related service entity")
    rating = models.PositiveIntegerField(default=5)
    comment = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service_type.title()} Review ({self.rating}⭐)"
