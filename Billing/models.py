import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import ValidationError

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
    customer_name=models.CharField(max_length=50)
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_invoices'
    )

    ''' @property
    def issued_to_name(self):
        # If related object exists
        obj = self.related_object

        if obj:
            # CASE 1: Booking Invoice → return guest name
            if hasattr(obj, 'guests'):   # Booking model ka signature
                # Agar multiple guests hain to first ka name return
                guest = obj.guests.first()
                if guest:
                    return guest.name

        # CASE 2: Default → issued_to user ka full name
        if self.issued_to:
            return self.issued_to.get_full_name() or self.issued_to.username

        return None'''

    def clean(self):
        if self.content_type and self.object_id:
            model_class = self.content_type.model_class()
            if not model_class.objects.filter(id=self.object_id).exists():
                raise ValidationError(
                    f"Referenced {model_class.__name__} with ID {self.object_id} does not exist"
                )
        elif bool(self.content_type) != bool(self.object_id):
            raise ValidationError(
                "Both content_type and object_id must be set together or both null"
            )
        if self.amount_paid and self.total_amount:
            if self.amount_paid > self.total_amount:
                raise ValidationError({
                    'amount_paid': f"Amount Paid ({self.amount_paid}) cannot be greater than Total Amount ({self.total_amount})."
                })

    def save(self, *args, **kwargs):
        self.full_clean()  # Ensure clean() is called before saving
        if not self.slug:
            year = timezone.now().year
            prefix = f"INV-{year}-"
            last = Invoice.objects.filter(slug__startswith=prefix).count() + 1
            self.slug = f"{prefix}{last:04d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.slug} ({self.status})"

    '''@property
    def balance_due(self):
        total_paid = self.payments.aggregate(total=models.Sum('amount_paid'))['total'] or 0
        return max(self.total_amount - total_paid, 0)'''
    
    @property
    def balance_due(self):
        return max(self.total_amount - self.amount_paid, 0)

    from django.db import transaction    
    @transaction.atomic
    def mark_as_paid(self, payment, reason=""):
        old_status = self.status
        self.status = 'paid'
        self.save()
        
        InvoiceStatusChange.objects.create(
            invoice=self,
            old_status=old_status,
            new_status='paid',
            reason=reason or f"Payment {payment.id} received"
        )
        
class InvoiceStatusChange(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='status_changes')
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    reason = models.TextField()
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice.slug} status changed from {self.old_status} to {self.new_status}"

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
    PAYMENT_STATUS = [('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    slug = models.SlugField(unique=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=100, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    reference = models.CharField(max_length=100, blank=True)
    
    @transaction.atomic
    def process(self):
        # Verify no duplicate transaction
        if Payment.objects.filter(transaction_id=self.transaction_id).exists():
            raise ValidationError("Duplicate payment transaction")
        
        self.save()
        
        # Update invoice atomically
        invoice = Invoice.objects.select_for_update().get(id=self.invoice.id)
        invoice.amount_paid = invoice.amount_paid + self.amount_paid
        invoice.status = 'paid' if invoice.amount_paid >= invoice.total_amount else 'partial'
        invoice.save()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.invoice.slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

        # ✅ Auto-update invoice status after payment
        total_paid = self.invoice.payments.aggregate(total=models.Sum('amount_paid'))['total'] or 0
        self.invoice.amount_paid = total_paid

        if total_paid >= self.invoice.total_amount:
            self.invoice.status = 'paid'
        elif total_paid > 0:
            self.invoice.status = 'partial'
        else:
            self.invoice.status = 'unpaid'
        
        self.invoice.save(update_fields=['amount_paid','status'])

    def __str__(self):
        return f"Payment {self.slug} ({self.method})"
