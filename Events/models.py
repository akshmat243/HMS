# events/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.text import slugify
import uuid


User = settings.AUTH_USER_MODEL

STATUS_CHOICES = (
    ("pending", "Pending"),
    ("confirmed", "Confirmed"),
    ("cancelled", "Cancelled"),
    ("completed", "Completed"),
)


class Venue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=255, blank=True, null=True, unique=True)
    kind = models.CharField(max_length=100, blank=True)  # Ballroom, Outdoor, Meeting Room
    capacity = models.PositiveIntegerField(default=0)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    features = models.JSONField(default=list, blank=True)  # list of tags e.g. ["WiFi","Projector"]
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="venues_created")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug_candidate = base_slug
            counter = 1
            while EventType.objects.filter(slug=slug_candidate).exists():
                slug_candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug_candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class EventType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, blank=True, null=True, unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            slug_candidate = uuid.uuid4().hex[:16]
            while EventType.objects.filter(slug=slug_candidate).exists():
                slug_candidate = uuid.uuid4().hex[:8]
            self.slug = slug_candidate

        super().save(*args, **kwargs)


    def __str__(self):
        return self.name


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True, null=True, unique=True)
    description = models.TextField(blank=True)
    event_type = models.ForeignKey(EventType, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    venue = models.ForeignKey(Venue, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    expected_guests = models.PositiveIntegerField(default=0)
    capacity_override = models.PositiveIntegerField(null=True, blank=True)  # optional override for capacity calc
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_created")
    contact_name = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    tags = models.JSONField(default=list, blank=True)  # e.g. ["Catering", "Audio/Visual"]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # amount paid so far
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            slug_candidate = uuid.uuid4().hex[:8]
            while Event.objects.filter(slug=slug_candidate).exists():
                slug_candidate = uuid.uuid4().hex[:8]
            self.slug = slug_candidate

        super().save(*args, **kwargs)


    class Meta:
        ordering = ["-start_datetime"]

    def __str__(self):
        return self.title

    @property
    def venue_capacity(self):
        if self.capacity_override:
            return self.capacity_override
        if self.venue and self.venue.capacity:
            return self.venue.capacity
        return 0

    @property
    def capacity_percent(self):
        cap = self.venue_capacity
        if not cap:
            return 0
        try:
            return round((self.expected_guests / cap) * 100, 1)
        except Exception:
            return 0

    @property
    def payment_percent(self):
        if not self.total_price:
            return 0
        try:
            return round((float(self.deposit_amount) / float(self.total_price)) * 100, 1)
        except Exception:
            return 0


class Event_Booking(models.Model):
    """
    Represents booking transactions / guest signups (optional).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    guests = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.pk} - {self.event.title}"
