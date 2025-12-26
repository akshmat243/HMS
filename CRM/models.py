import uuid
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.db.models import Sum
from Hotel.models import Hotel

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
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_lead')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='crm_leads', null=True, blank=True)
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, blank=True)
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

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            new_slug = base_slug
            counter = 1
            while Lead.objects.filter(slug=new_slug).exists():
                new_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = new_slug
        super().save(*args, **kwargs)


class Customer(models.Model):
    CUSTOMER_TYPES = [
        ('vip', 'VIP'),
        ('regular', 'Regular'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive','Inactive'),
    ]

    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='customer_created')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='crm_customers', null=True, blank=True)
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, blank=True)
    image = models.ImageField(upload_to='crm/customers/', blank=True, null=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True) 
    country = models.CharField(max_length=100, blank=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPES, default='regular')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    loyalty_points = models.PositiveIntegerField(default=0)
    preferences = models.TextField(blank=True, help_text="Comma separated tags e.g. Ocean View, Late Checkout") 
    feedback = models.TextField(blank=True)
    last_visit = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('hotel', 'email')


    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            new_slug = base_slug
            counter = 1
            while Customer.objects.filter(slug=new_slug).exists():
                new_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = new_slug
        super().save(*args, **kwargs)


    def update_loyalty_points(self):
        from Billing.models import Invoice # Circular import avoid karne ke liye andar import kiya
        
        # 1. Total paid amount nikalein (Sirf 'paid' invoices ka)
        total_spent = Invoice.objects.filter(
            issued_to__email=self.email, 
            status='paid'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # 2. Calculation logic: $2.21 spent = 1 point
        # Decimal use kar rahe hain precision ke liye
        conversion_rate = Decimal('2.21')
        
        if total_spent > 0:
            # int() lagaya hai taaki points round figure mein aaye (e.g. 10.5 nahi 10)
            self.loyalty_points = int(total_spent / conversion_rate)
        else:
            self.loyalty_points = 0
            
        self.save()


class Interaction(models.Model):
    METHOD_CHOICES = [
        ('call', 'Call'),
        ('email', 'Email'),
        ('meeting', 'Meeting'),
        ('message', 'Message'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="crm_interaction", null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='interactions')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    notes = models.TextField()
    date = models.DateTimeField()
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='interactions_handled')

    def __str__(self):
        return f"{self.method.title()} - {self.customer.name}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.customer.name}-{uuid.uuid4().hex[:6]}"
            self.slug = slugify(base)
        super().save(*args, **kwargs)
