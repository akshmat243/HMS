import uuid
from django.db import models
from django.utils.text import slugify
from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

class Hotel(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('maintenance', 'Maintenance'),
        ('closed', 'Closed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='hotel',
        limit_choices_to={'role__name': 'Admin'},
        help_text="The admin user who owns this hotel"
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            
         # Enforce single hotel per admin
        if self.owner and Hotel.objects.exclude(id=self.id).filter(owner=self.owner).exists():
            raise ValueError(f"Admin {self.owner.full_name} already owns a hotel.")
        super().save(*args, **kwargs)




class RoomCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='room_categories')
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    max_occupancy = models.PositiveIntegerField()
    amenities = models.TextField(help_text="Comma-separated list of amenities")
    image = models.ImageField(upload_to='hotel/room_categories/', blank=True, null=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)

    def __str__(self):
        return f"{self.name} - {self.hotel.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            index = 1
            while RoomCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{index}"
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Room(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('reserved', 'Reserved'),
        ('maintenance', 'Maintenance'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='rooms')
    room_category = models.ForeignKey(RoomCategory, on_delete=models.SET_NULL, null=True, related_name='rooms')

    room_number = models.CharField(max_length=20, blank=True)
    room_code = models.CharField(max_length=20, unique=True, help_text="Unique code for internal identification")
    slug = models.SlugField(unique=True, blank=True)

    floor = models.CharField(max_length=20)
    is_available = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    # Extended fields
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amenities = models.TextField(blank=True, help_text="Optional: Comma-separated list specific to this room")
    bed_type = models.CharField(max_length=50, blank=True, help_text="e.g. King, Queen, Twin")
    room_size = models.CharField(max_length=50, blank=True, help_text="e.g. 30 sqm, 350 sqft")
    view = models.CharField(max_length=100, blank=True, help_text="e.g. Sea View, City View, Garden View")
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('hotel', 'room_number')
        ordering = ['hotel', 'room_number']

    def __str__(self):
        return f"{self.room_number} - {self.hotel.name}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.room_number:
                count = Room.objects.filter(hotel=self.hotel, floor=self.floor).count() + 1
                try:
                    floor_number = int(self.floor)
                    self.room_number = f"R{floor_number}{count:02d}"
                except ValueError:
                    self.room_number = f"R{self.floor}{count:02d}"

                while Room.objects.filter(hotel=self.hotel, room_number=self.room_number).exists():
                    count += 1
                    try:
                        floor_number = int(self.floor)
                        self.room_number = f"R{floor_number}{count:02d}"
                    except ValueError:
                        self.room_number = f"R{self.floor}{count:02d}"

            if not self.slug:
                base_slug = slugify(f"{self.hotel.name}-{self.room_number}")
                slug = base_slug
                index = 1
                while Room.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{index}"
                    index += 1
                self.slug = slug

            # Auto-generate room_code if not set
            # if not self.room_code:
            #     self.room_code = f"RM-{uuid.uuid4().hex[:8].upper()}"

            # Default room price from category if not manually set
            if not self.price_per_night and self.room_category:
                self.price_per_night = self.room_category.price_per_night

            super().save(*args, **kwargs)


class RoomMedia(models.Model):
    ROOM_MEDIA_TYPE = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='hotel/rooms/media/')
    media_type = models.CharField(max_length=10, choices=ROOM_MEDIA_TYPE, default='image')
    caption = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.media_type.capitalize()} for {self.room.room_number}"


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
    booking_code = models.CharField(max_length=10, unique=True, blank=True)
    slug = models.SlugField(unique=True, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    guests_count = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='unpaid')
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.hotel.name} - {self.status}"
    
    def save(self, *args, **kwargs):
        if not self.booking_code:
            last = Booking.objects.order_by('-created_at').first()
            if last and last.booking_code and last.booking_code.startswith('BK'):
                last_number = int(last.booking_code.replace('BK', ''))
                self.booking_code = f"BK{last_number + 1:03d}"
            else:
                self.booking_code = "BK001"

        if not self.slug:
            self.slug = slugify(self.booking_code)

        super().save(*args, **kwargs)
        if self.status == "checked_out" and self.room:
            self.room.is_available = True
            self.room.save(update_fields=["is_available"])
        
        
class Guest(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='guests')
    slug = models.SlugField(unique=True, blank=True)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    id_proof_type = models.CharField(max_length=50, blank=True, null=True)
    id_proof_number = models.CharField(max_length=50, blank=True, null=True)
    special_request = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''} ({self.booking.booking_code})".strip()

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.first_name}-{self.last_name or ''}-{self.booking.booking_code}")
            counter = 1
            new_slug = base_slug
            while Guest.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug
        super().save(*args, **kwargs)
    
    

class RoomServiceRequest(models.Model):
    SERVICE_CHOICES = [
        ('food', 'Food'),
        ('laundry', 'Laundry'),
        ('amenities', 'Amenities'),
        ('cleaning', 'Cleaning'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('ready', 'Ready for Delivery'),
        ('delivered', 'Delivered'),
    ]

    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('express', 'Express'),
    ]

    SERVICE_RATES = {
        'laundry': 50,      # ₹50 per item
        'food': 0,          # handled separately
        'amenities': 0,     # usually free
        'cleaning': 100,    # fixed
        'other': 0,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    service_code = models.CharField(max_length=30, unique=True, editable=False)

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="room_services")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="room_services")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="service_requests")

    service_type = models.CharField(max_length=50, choices=SERVICE_CHOICES)
    description = models.JSONField(default=dict, help_text="e.g. {'items': [{'name': 'Shirt', 'qty': 3}]}")

    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    base_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    requested_at = models.DateTimeField(auto_now_add=True)
    pickup_time = models.TimeField(null=True, blank=True)
    delivery_time = models.TimeField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.service_code} - {self.service_type} - Room {self.room.room_number}"

    def calculate_cost(self):
        rate = self.SERVICE_RATES.get(self.service_type, 0)

        if self.service_type == 'laundry':
            items = self.description.get('items', [])
            total_qty = sum(item.get('qty', 1) for item in items)
            return rate * total_qty

        elif self.service_type == 'cleaning':
            return rate

        elif self.service_type == 'food':
            return 0

        else:
            return rate

    def save(self, *args, **kwargs):
        # ✅ Auto-generate service_code
        if not self.service_code:
            year = timezone.now().year
            hotel_code = slugify(self.room.hotel.name)[:5].upper() if self.room and self.room.hotel else "HOTEL"
            prefix = f"SRV-{hotel_code}-{year}-"
            last_code = RoomServiceRequest.objects.filter(service_code__startswith=prefix).aggregate(max_code=Max('service_code'))['max_code']

            if last_code:
                try:
                    last_number = int(last_code.split('-')[-1])
                except (ValueError, IndexError):
                    last_number = 0
                next_number = last_number + 1
            else:
                next_number = 1

            self.service_code = f"{prefix}{next_number:04d}"

        # ✅ Auto-generate slug
        if not self.slug:
            hotel_part = slugify(self.room.hotel.name) if self.room and self.room.hotel else "hotel"
            base_slug = f"{hotel_part}-{self.service_type}-{self.room.room_number}-{self.service_code}"
            self.slug = slugify(base_slug)

        # ✅ Auto-calculate costs
        self.base_cost = self.SERVICE_RATES.get(self.service_type, 0)
        total = self.calculate_cost()
        self.total_cost = total
        self.cost = total
        is_new = self._state.adding  # Check if this is a new instance
        super().save(*args, **kwargs)
        
        # ✅ Auto-create invoice if new and no existing invoice linked
        from Billing.models import Invoice, InvoiceItem
        from django.contrib.contenttypes.models import ContentType
        if is_new:
            content_type = ContentType.objects.get_for_model(RoomServiceRequest)
            invoice = Invoice.objects.create(
                content_type=content_type,
                object_id=self.id,
                issued_to=self.user,
                total_amount=self.total_cost,
                status='unpaid'
            )

            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"Room Service - {self.service_type.title()} ({self.room.room_number})",
                quantity=1,
                unit_price=self.total_cost,
            )
        
        if not self._state.adding:

             # Update linked invoice if exists
            content_type = ContentType.objects.get_for_model(RoomServiceRequest)
            invoice = Invoice.objects.filter(content_type=content_type, object_id=self.id).first()

            if invoice:
                invoice.total_amount = self.total_cost
                invoice.save(update_fields=["total_amount"])

                invoice.items.all().delete()
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=f"Updated Room Service - {self.service_type.title()}",
                    quantity=1,
                    unit_price=self.total_cost,
                )