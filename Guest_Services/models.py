import uuid
from Hotel.models import Booking
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model
User = get_user_model()
from Hotel.models import Hotel
from Restaurant.models import Restaurant

class ServiceCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True, related_name='category_hotel')
    # restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, null= True, related_name='category_restaurant')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_categories_created"
    )
    preference_tags = models.JSONField(default=list, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class GuestService(models.Model):
    STATUS_CHOICES = (
        ("available", "Available"),
        ("unavailable", "Unavailable"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True, related_name='servie_hotel')
    # restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, null= True, related_name='supplier_restaurant')
    name = models.CharField(max_length=150)
    icon = models.CharField(max_length=50,blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name="services")

    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.PositiveIntegerField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="available")

    rating = models.FloatField(default=0)
    total_bookings = models.PositiveIntegerField(default=0)


    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,blank=True, related_name='guest_services_created')

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug = base_slug
            counter = 1

            while GuestService.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = unique_slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name



class ServiceRequest(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    PRIORITY_CHOICES = (
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    )

    # booking = models.ForeignKey("hotel.Booking", on_delete=models.CASCADE,related_name="service_requests")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True, related_name='service_request_hotel')
    # restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, null= True, related_name='supplier_restaurant')
    icon = models.CharField(max_length=50,blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True)
    booking = models.ForeignKey('Hotel.Booking', on_delete=models.CASCADE, related_name="service_requests")

    service_type = models.CharField(max_length=150)  # e.g. Restaurant Reservation
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.CASCADE,
        related_name="service_requests"
    )

    guest_name = models.CharField(max_length=50)
    guest_room = models.CharField(max_length=20)

    schedule_datetime = models.DateTimeField()

    description = models.TextField(blank=True)

    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_service_requests"
    )

    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    rating = models.FloatField(null=True, blank=True)


    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,blank=True, related_name='guest_request_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.service_type}-{self.booking.booking_code}"
            base_slug = slugify(base)
            slug = base_slug
            counter = 1
            while ServiceRequest.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service_type} for {self.guest_name} ({self.guest_room})"
