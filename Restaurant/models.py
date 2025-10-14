import uuid
from django.db import models
from django.utils.text import slugify
from Hotel.models import Hotel
from django.contrib.auth import get_user_model

User = get_user_model()

class MenuCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='menu_categories')
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.hotel.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            counter = 1
            new_slug = base_slug
            while MenuCategory.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug
        super().save(*args, **kwargs)


class MenuItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to='restaurant/menu_items/', blank=True, null=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            counter = 1
            new_slug = base_slug
            while MenuItem.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug
        super().save(*args, **kwargs)


class Table(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('occupied', 'Occupied'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='tables')
    number = models.CharField(max_length=10)
    slug = models.SlugField(unique=True, blank=True)
    table_code = models.CharField(max_length=10, unique=True, blank=True)
    capacity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    def __str__(self):
        return f"Table {self.number} - {self.hotel.name}"

    def save(self, *args, **kwargs):
        if not self.table_code:
            last_table = Table.objects.order_by('-table_code').first()
            if last_table and last_table.table_code.startswith('T'):
                last_number = int(last_table.table_code[1:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.table_code = f"T{new_number:02d}"  # e.g., T01, T02, T10

        if not self.slug:
            base_slug = slugify(f"{self.hotel.name}-{self.number}")
            counter = 1
            new_slug = base_slug
            while Table.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug

        super().save(*args, **kwargs)


class RestaurantOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('served', 'Served'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='restaurant_orders')
    guest_name = models.CharField(max_length=100)
    guest_phone = models.CharField(max_length=15)
    remarks = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    order_time = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Order {self.slug or self.id} - {self.guest_name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"order-{uuid.uuid4().hex[:6]}")
            self.slug = base_slug
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name='order_items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.menu_item.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.menu_item.name}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

class TableReservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='reservations')
    slug = models.SlugField(unique=True, blank=True)

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    special_occasion = models.CharField(max_length=100, blank=True, null=True)
    special_requests = models.TextField(blank=True, null=True)

    reservation_date = models.DateField()
    reservation_time = models.TimeField()
    people_count = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.table} ({self.reservation_date} {self.reservation_time})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.full_name}-{self.reservation_date}-{self.reservation_time}")
            counter = 1
            new_slug = base_slug
            while TableReservation.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug
        super().save(*args, **kwargs)