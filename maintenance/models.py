import uuid
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from Hotel.models import Hotel, Room, Guest

User = get_user_model()


class MaintenanceCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="maintenance_categories")
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('hotel', 'name')
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            counter = 1
            while MaintenanceCategory.objects.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}"


class MaintenanceTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="maintenance_tasks")
    category = models.ForeignKey(MaintenanceCategory, on_delete=models.SET_NULL, null=True, related_name="tasks")

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="maintenance_tasks")
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.SET_NULL, related_name="maintenance_tasks")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__name': 'Staff'},
        related_name='assigned_maintenance_tasks'
    )

    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_maintenance_tasks')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.title}-{str(self.id)[:6]}")
            self.slug = base
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.status})"


class RoomCleaningSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="cleaning_schedules")
    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="cleaning_status")

    last_cleaned = models.DateField(null=True, blank=True)
    next_cleaning = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cleaning for {self.room.room_number}"
