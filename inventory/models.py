from django.db import models
from django.utils.text import slugify
from datetime import date
import uuid
from django.conf import settings

class Supplier(models.Model):
    slug = models.SlugField(unique=True, blank=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    rating = models.FloatField(default=0.0)

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
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='inventory_admin', null=True,
    blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            index = 1
            while InventoryCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{index}"
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    STATUS_CHOICES = [
        ("good", "Good"),
        ("low", "Low"),
        ("critical", "Critical"),
        ("overstock", "Overstock"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True)
    stock_level = models.FloatField(default=0)
    unit = models.CharField(max_length=50, default="units")
    min_stock = models.FloatField(default=0)
    max_stock = models.FloatField(default=0)
    cost_per_unit = models.FloatField(default=0)
    total_value = models.FloatField(default=0)
    last_restocked = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="good")
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='item_admin', null=True,
    blank=True)

    def save(self, *args, **kwargs):
        # Auto-calculate total value
        self.total_value = round(self.stock_level * self.cost_per_unit, 2)

        # Auto-update status
        if self.stock_level == 0:
            self.status = "critical"
        elif self.stock_level < self.min_stock:
            self.status = "low"
        elif self.stock_level > self.max_stock:
            self.status = "overstock"
        else:
            self.status = "good"

        # Default restock date
        if not self.last_restocked:
            self.last_restocked = date.today()

        # Generate unique slug (same as RoomCategory approach)
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            index = 1
            while InventoryItem.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{index}"
                index += 1
            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default="Pending")
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchase_admin', null=True,
    blank=True)

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

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.item.name}-{self.order.id}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

    @property
    def total_cost(self):
        return self.quantity * self.cost_per_unit
