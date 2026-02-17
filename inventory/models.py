from django.db import models
from django.utils.text import slugify
from datetime import date
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError


class Supplier(models.Model):
    slug = models.SlugField(unique=True, blank=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    rating = models.FloatField(default=0.0)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='supplier_profile'
    )
    hotel = models.ForeignKey("Hotel.Hotel", on_delete=models.CASCADE, null=True, blank=True, related_name='supplier')
    restaurant = models.ForeignKey("Restaurant.Restaurant", on_delete=models.CASCADE, null= True, related_name='supplier_restaurant')

    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='supplier_admin', null=True,
    blank=True)


    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            index = 1
            # ensure unique slug for suppliers
            while Supplier.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{index}"
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class InventoryCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_categories"
    )

    hotel = models.ForeignKey(
        "Hotel.Hotel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_categories"
    )

    restaurant = models.ForeignKey(
        "Restaurant.Restaurant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_categories"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(hotel__isnull=False, restaurant__isnull=True) |
                    models.Q(hotel__isnull=True, restaurant__isnull=False)
                ),
                name="category_hotel_or_restaurant_only"
            ),
            models.UniqueConstraint(
                fields=["name", "hotel", "restaurant"],
                name="unique_category_per_entity"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while InventoryCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

from decimal import Decimal
from django.core.exceptions import ValidationError

class InventoryItem(models.Model):
    STATUS_CHOICES = [
        ("good", "Good"),
        ("low", "Low"),
        ("critical", "Critical"),
        ("overstock", "Overstock"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    category = models.ForeignKey(
        InventoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        related_name="items"
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    stock_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    unit = models.CharField(max_length=50, default="units")

    min_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    max_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    cost_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    total_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    last_restocked = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="good"
    )

    managed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items"
    )

    hotel = models.ForeignKey(
        "Hotel.Hotel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_items"
    )

    restaurant = models.ForeignKey(
        "Restaurant.Restaurant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_items"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(hotel__isnull=False, restaurant__isnull=True) |
                    models.Q(hotel__isnull=True, restaurant__isnull=False)
                ),
                name="item_hotel_or_restaurant_only"
            ),
        ]

    def clean(self):
        if self.hotel and self.restaurant:
            raise ValidationError("Item cannot belong to both hotel and restaurant.")

    def save(self, *args, **kwargs):
        # Calculate total value
        self.total_value = self.stock_level * self.cost_per_unit

        # Update status
        if self.stock_level <= 0:
            self.status = "critical"
        elif self.stock_level < self.min_stock:
            self.status = "low"
        elif self.max_stock and self.stock_level > self.max_stock:
            self.status = "overstock"
        else:
            self.status = "good"

        # Slug
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while InventoryItem.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return self.stock_level < self.min_stock

    @property
    def is_out_of_stock(self):
        return self.stock_level <= 0

    def __str__(self):
        return self.name


class InventoryAlert(models.Model):
    ALERT_LEVELS = [
        ("low", "Low"),
        ("critical", "Critical"),
    ]

    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="alerts"
    )
    level = models.CharField(max_length=20, choices=ALERT_LEVELS)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item.name} - {self.level}"


class InventoryReorder(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    requested_qty = models.FloatField()
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("ordered", "Ordered"),
            ("received", "Received"),
        ],
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default="Pending")
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchase_admin', null=True,
    blank=True)
    hotel = models.ForeignKey("Hotel.Hotel", on_delete=models.CASCADE, null=True, blank=True, related_name='order_hotel')
    restaurant = models.ForeignKey("Restaurant.Restaurant", on_delete=models.CASCADE, null= True, related_name='order_restaurant')

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"po-{uuid.uuid4().hex[:6]}")
            self.slug = base_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PO-{self.id} ({self.supplier.name})"


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    cost_per_unit = models.FloatField()
    slug = models.SlugField(unique=True, blank=True)
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchase_item_admin', null=True,
    blank=True)
    hotel = models.ForeignKey("Hotel.Hotel", on_delete=models.CASCADE, null=True, blank=True, related_name='order_item')
    restaurant = models.ForeignKey("Restaurant.Restaurant", on_delete=models.CASCADE, null= True, related_name='order_item_restaurant')

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.item.name}-{self.order.id}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

    @property
    def total_cost(self):
        return self.quantity * self.cost_per_unit
