import uuid
from django.db import models
from django.utils.text import slugify
from Hotel.models import Hotel
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class Restaurant(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        # ('maintenance', 'Maintenance'),
        ('closed', 'Closed'),
    ]

    CATEGORY_CHOICES = [
        ('japanese', 'Japanese'),
        ('Italian Fine Dining', 'italian fine dining'),
        ('Seafood & Steakhouse', 'seafood & steakhouse'),
        ('Modern European', 'modern european'),
        ('American Comfort', 'american comfort'),
        ('Indian', 'indian')
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='restaurant',
        limit_choices_to={'role__name': 'Admin'},
        help_text="The admin user who owns this Restaurant"
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Indian')
    amenities = models.TextField(help_text="Comma-separated list of amenities")
    rating = models.DecimalField(
    max_digits=2,
    decimal_places=1,
    validators=[MinValueValidator(1), MaxValueValidator(5)],
    help_text="Rating must be between 1.0 and 5.0"
)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    contact_number = models.CharField(max_length=15)
    email = models.EmailField()
    logo = models.ImageField(upload_to='restaurant/logos/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='restaurant/covers/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            
         # Enforce single hotel per admin
        if self.owner and Restaurant.objects.exclude(id=self.id).filter(owner=self.owner).exists():
            raise ValueError(f"Admin {self.owner.full_name} already owns a Restaurant.")
        super().save(*args, **kwargs)

class MenuCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="menu_categories"
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.restaurant.name}"

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
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="tables"
    )
    number = models.CharField(max_length=10)
    slug = models.SlugField(unique=True, blank=True)
    table_code = models.CharField(max_length=10, unique=True, blank=True)
    capacity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    status_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Table {self.number} - {self.restaurant.name}"

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
            base_slug = slugify(f"{self.restaurant.name}-{self.number}")
            counter = 1
            new_slug = base_slug
            while Table.objects.filter(slug=new_slug).exists():
                counter += 1
                new_slug = f"{base_slug}-{counter}"
            self.slug = new_slug
        if self.pk:
            old = Table.objects.filter(pk=self.pk).first()
            if old and old.status != self.status:
                self.status_updated_at = timezone.now()

        super().save(*args, **kwargs)
    
    def get_last_status_time(self):
        # from Restaurant.models import RestaurantOrder

        now = timezone.now()

        # If table is available → use table.status_updated_at
        if self.status == "available":
            if self.status_updated_at:
                diff = now - self.status_updated_at
                return int(diff.total_seconds() / 60)
            return None

        # If table is not available → fetch last active order
        active_status = ['pending', 'preparing', 'served']

        order = RestaurantOrder.objects.filter(
            table=self,
            status__in=active_status
        ).order_by('-status_updated_at').first()

        if order and order.status_updated_at:
            diff = now - order.status_updated_at
            return int(diff.total_seconds() / 60)

        # If table has no active order, fall back to table timestamp
        if self.status_updated_at:
            diff = now - self.status_updated_at
            return int(diff.total_seconds() / 60)

        return None


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
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="orders"
    )
    guest_name = models.CharField(max_length=100)
    guest_phone = models.CharField(max_length=15)
    remarks = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    total_quantity = models.PositiveIntegerField(default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_rule = models.ForeignKey('DiscountRule', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    order_code = models.CharField(max_length=20, unique=True)
    order_time = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status_updated_at = models.DateTimeField(null=True, blank=True)

    def get_applicable_discount_rule(self):
        """Return the active discount rule 
            that matches subtotal."""
        subtotal = self.subtotal or Decimal('0.00') 
        applicable_rules = DiscountRule.objects.filter(is_active=True).order_by('-min_amount') 
        
        for rule in applicable_rules: 
            if rule.applies_to(subtotal): 
                return rule 
        return None
    
    
    def save(self, *args, **kwargs):
        is_new = self._state.adding

        # ✅ Generate order code
        if is_new and not self.order_code:
            last = RestaurantOrder.objects.order_by('-order_time').first()
            next_number = 1

            if last and last.order_code:
                try:
                    next_number = int(last.order_code.replace("ORD", "")) + 1
                except:
                    pass

            self.order_code = f"ORD{next_number:03d}"

        # ✅ Generate slug
        if not self.slug:
            self.slug = slugify(f"{self.restaurant.slug}-{self.order_code}")

        # ✅ Status change timestamp
        if not is_new:
            old = RestaurantOrder.objects.filter(pk=self.pk).first()
            if old and old.status != self.status:
                self.status_updated_at = timezone.now()

                # ✅ Mark completed time
                if self.status == "completed":
                    self.completed_at = timezone.now()

        # ✅ New order initial timestamp
        if is_new and not self.status_updated_at:
            self.status_updated_at = timezone.now()

        # ✅ Calculate totals BEFORE final save
        items = list(self.order_items.all())
        self.total_quantity = sum(i.quantity for i in items)
        self.subtotal = sum(i.price * i.quantity for i in items)

        self.sgst = (self.subtotal * Decimal('0.025')).quantize(Decimal('0.01'))
        self.cgst = (self.subtotal * Decimal('0.025')).quantize(Decimal('0.01'))

        rule = self.get_applicable_discount_rule()
        self.discount_rule = rule

        if rule:
            self.discount = (self.subtotal * rule.percentage / Decimal('100')).quantize(Decimal('0.01'))
        else:
            self.discount = Decimal('0.00')

        total_after_tax = self.subtotal + self.sgst + self.cgst
        self.grand_total = (total_after_tax - self.discount).quantize(Decimal('0.01'))

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_code} - {self.guest_name}"



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
        
class DiscountRule(models.Model):
    name = models.CharField(max_length=100, help_text="Name or label for this discount rule.")
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Minimum order amount to apply discount.")
    max_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Maximum order amount (leave blank for no limit).")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Discount percentage (e.g., 10 for 10%).")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['min_amount']
        verbose_name = "Discount Rule"
        verbose_name_plural = "Discount Rules"

    def __str__(self):
        return f"{self.name} ({self.percentage}% off for ≥ ₹{self.min_amount})"

    def applies_to(self, subtotal: Decimal) -> bool:
        """Return True if this rule applies for the given subtotal."""
        if not self.is_active:
            return False
        if self.max_amount and subtotal > self.max_amount:
            return False
        return subtotal >= self.min_amount

class BookingCallback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    restaurant_name = models.CharField(max_length=150) 
    phone_number = models.CharField(max_length=15)
    preferred_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False) # CRM status ke liye

    def __str__(self):
        return f"Callback: {self.restaurant_name} - {self.phone_number}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.restaurant_name}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)