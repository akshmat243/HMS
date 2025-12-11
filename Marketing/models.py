import uuid
from django.db import models
from django.utils.text import slugify
from Hotel.models import Hotel


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
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="campaign")
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    type = models.CharField(
        max_length=20,
        choices=CAMPAIGN_TYPE_CHOICES,
        default='email',
        help_text='Channel / campaign type'
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

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def _str_(self):
        return self.name
    
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
    