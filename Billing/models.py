import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

User = get_user_model()


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)

    # 🔗 Dynamic link to any app model (Booking, RestaurantOrder, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    issued_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_invoices')
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            year = timezone.now().year
            prefix = f"INV-{year}-"
            last = Invoice.objects.filter(slug__startswith=prefix).count() + 1
            self.slug = f"{prefix}{last:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.slug} ({self.status})"

    @property
    def balance_due(self):
        total_paid = self.payments.aggregate(total=models.Sum('amount_paid'))['total'] or 0
        return max(self.total_amount - total_paid, 0)


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    slug = models.SlugField(unique=True, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        if not self.slug:
            base = f"{self.description[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} - {self.amount}"


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

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.invoice.slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

        # ✅ Auto-update invoice status after payment
        total_paid = self.invoice.payments.aggregate(total=models.Sum('amount_paid'))['total'] or 0
        if total_paid >= self.invoice.total_amount:
            self.invoice.status = 'paid'
        elif total_paid > 0:
            self.invoice.status = 'partial'
        else:
            self.invoice.status = 'unpaid'
        self.invoice.save(update_fields=['status'])

    def __str__(self):
        return f"Payment {self.slug} ({self.method})"
