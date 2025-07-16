import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Lead(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('interested', 'Interested'),
        ('converted', 'Converted'),
        ('lost', 'Lost'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    source = models.CharField(max_length=100, blank=True)
    interest_level = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_leads')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    feedback = models.TextField(blank=True)
    loyalty_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Interaction(models.Model):
    METHOD_CHOICES = [
        ('call', 'Call'),
        ('email', 'Email'),
        ('meeting', 'Meeting'),
        ('message', 'Message'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='interactions')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    notes = models.TextField()
    date = models.DateTimeField()
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='interactions_handled')

    def __str__(self):
        return f"{self.method.title()} - {self.customer.name}"
