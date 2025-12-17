import uuid
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from django.conf import settings
from django.utils import timezone

User = get_user_model()


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    sent_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.title[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=255)
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.subject[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject} from {self.sender} to {self.receiver}"


class Feedback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='feedbacks')
    message = models.TextField()
    rating = models.PositiveIntegerField(default=5)  # 1 to 5
    submitted_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.message[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Feedback from {self.user} ({self.rating}⭐)"


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
    



User = settings.AUTH_USER_MODEL
class OutgoingMessage(models.Model):
    CHANNEL_CHOICES = (('email','Email'),('whatsapp','WhatsApp'),('sms','SMS'))
    STATUS_CHOICES = (('pending','Pending'),('scheduled','Scheduled'),('sent','Sent'),('pending_click','Pending (click)'),('failed','Failed'))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    recipient = models.CharField(max_length=255)        # email or phone
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='outgoing_messages')
    created_at = models.DateTimeField(auto_now_add=True)
    # added schedule_at so code that writes schedule_at won't break
    schedule_at = models.DateTimeField(null=True, blank=True)
    hotel_slug = models.SlugField(max_length=100, blank=True)

    template_used = models.ForeignKey(
        'MessageTemplate', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='usage_history'
    )
    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{(self.subject or '')[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)

    def mark_sent(self):
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.channel} -> {self.recipient} ({self.status})"


# --- MessageTemplate (replace existing) ---
class MessageTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    name = models.CharField(max_length=200)
    channel = models.CharField(max_length=20, choices=(('email','email'),('whatsapp','whatsapp'),('sms','sms')))
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)   # added for updates

    def save(self, *args, **kwargs):
        # create slug from name (not from non-existent self.message)
        if not self.slug:
            base = f"{self.name[:30]}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        # if updating existing record, set updated_at
        if self.pk:
            self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name