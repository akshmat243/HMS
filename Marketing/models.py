from decimal import Decimal
import uuid
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db.models import Sum
User = get_user_model()

from Hotel.models import Hotel


from django.db import models
from django.db.models import Sum
from decimal import Decimal
from django.utils.text import slugify
import uuid

class Campaign(models.Model):
    CAMPAIGN_TYPE_CHOICES = [
        ('email', 'Email'),
        ('social', 'Social Media'),
        ('sms', 'SMS'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="campaigns"
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    type = models.CharField(
        max_length=20,
        choices=CAMPAIGN_TYPE_CHOICES,
        default='email'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    start_date = models.DateField()
    end_date = models.DateField()

    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    results = models.TextField(
        blank=True,
        help_text="Final outcome, metrics, or analysis"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            counter = 1
            slug = base
            while Campaign.objects.filter(slug=slug).exists():
                counter += 1
                slug = f"{base}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    # -------------------------------
    # 💰 BUDGET & SPEND
    # -------------------------------
    @property
    def total_spent(self):
        return self.expenses.aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")

    @property
    def remaining_budget(self):
        return self.budget - self.total_spent

    @property
    def budget_used_percent(self):
        if self.budget == 0:
            return 0
        return round((self.total_spent / self.budget) * 100, 2)

    # -------------------------------
    # 📈 ROI
    # -------------------------------
    @property
    def total_revenue(self):
        from Hotel.models import Booking
        return Booking.objects.filter(
            campaign=self,
            payment_status="paid"
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")

    @property
    def roi_percent(self):
        if self.total_spent == 0:
            return 0
        return round(
            ((self.total_revenue - self.total_spent) / self.total_spent) * 100,
            2
        )

    # -------------------------------
    # 🚨 ALERTS
    # -------------------------------
    def budget_alert_level(self):
        percent = self.budget_used_percent
        if percent >= 100:
            return "critical"
        if percent >= 80:
            return "warning"
        return "ok"



# marketing/models.py
class CampaignExpense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="expenses"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_type = models.CharField(
        max_length=50,
        choices=[
            ("ads", "Ads"),
            ("influencer", "Influencer"),
            ("email", "Email Marketing"),
            ("sms", "SMS"),
            ("tools", "Tools"),
            ("other", "Other"),
        ]
    )

    reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Invoice ID / Transaction ID"
    )

    spent_on = models.DateField()
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-spent_on"]

    
class CampaignEvent(models.Model):
    
    EVENT_CHOICES = [
        ('impression', 'Impression'),
        ('click', 'Click'),
        ('conversion', 'Conversion'),
    ]
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="campaignevent")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.CASCADE,
        related_name='events'
    )
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    user_id = models.CharField(max_length=200, null=True, blank=True)
    session_id = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def _str_(self):
        return f"{self.campaign.name} - {self.event_type}"
    
    


class Promotion(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="promotion")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    content = models.TextField()
    promo_image = models.ImageField(upload_to='marketing/promotions/', blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def _str_(self):
        return self.title
    