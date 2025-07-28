import uuid
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from Hotel.models import Booking

User = get_user_model()

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='invoices')
    issued_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_invoices')
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.booking.id}-{self.issued_at.timestamp()}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice #{self.slug} - {self.status}"


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.description
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.description[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('wallet', 'Wallet'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    slug = models.SlugField(unique=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Payment for Invoice {self.invoice.slug}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.invoice.slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)
