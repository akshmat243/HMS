import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Hotel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    contact_number = models.CharField(max_length=15)
    email = models.EmailField()
    logo = models.ImageField(upload_to='hotel/logos/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='hotel/covers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class RoomCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='room_categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    max_occupancy = models.PositiveIntegerField()
    amenities = models.TextField(help_text="Comma-separated list of amenities")
    image = models.ImageField(upload_to='hotel/room_categories/', blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.hotel.name}"


class Room(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('maintenance', 'Maintenance'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='rooms')
    room_category = models.ForeignKey(RoomCategory, on_delete=models.SET_NULL, null=True, related_name='rooms')
    room_number = models.CharField(max_length=20)
    floor = models.CharField(max_length=20)
    is_available = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    def __str__(self):
        return f"{self.room_number} - {self.hotel.name}"


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
    ]

    PAYMENT_STATUS = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('partial', 'Partial'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    check_in = models.DateField()
    check_out = models.DateField()
    guests_count = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='unpaid')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.hotel.name} - {self.status}"

class RoomServiceRequest(models.Model):
    SERVICE_CHOICES = [
        ('food', 'Food'),
        ('laundry', 'Laundry'),
        ('amenities', 'Amenities'),
        ('cleaning', 'Cleaning'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='room_services')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='room_services')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='service_requests')
    service_type = models.CharField(max_length=50, choices=SERVICE_CHOICES)
    description = models.TextField(help_text="Details of the request (e.g. 2 towels, 1 sandwich)")
    requested_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.service_type.title()} for Room {self.room.room_number}"
