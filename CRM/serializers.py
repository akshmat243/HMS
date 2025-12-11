from rest_framework import serializers
from django.db.models import Sum, Q
from django.contrib.auth import get_user_model
from .models import Lead, Customer, Interaction
from Hotel.models import Booking, Guest
from Restaurant.models import TableReservation
from Billing.models import Invoice
from django.utils import timezone
import re # regex for MObile NUmber validations

User = get_user_model()

def validate_phone_number(value):
    if not re.match(r'^\+?1?\d{9,15}$',value):
        raise serializers.ValidationError("phone number must be (9-15 chars) digit")
    return value

class LeadSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)
    assigned_to = serializers.SlugRelatedField(
        slug_field='email', # Changed to email or full_name as per your preference
        queryset=User.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ['hotel', 'created_by']

    def validate_phone(self,value):
        return validate_phone_number(value)

    def validate_email(self, value):
        request = self.context.get('request')
        hotel = getattr(request.user, 'hotel', None) if request else None

        qs = Lead.objects.filter(email=value, hotel=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A lead with this email already exists.")
        return value


class CustomerSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)
    loyalty_points = serializers.IntegerField(read_only=True)
    
    # Custom Fields for CRM Dashboard
    total_bookings_count = serializers.SerializerMethodField()
    total_spent_amount = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = '__all__' 
        read_only_fields = ['hotel','created_by']
        # Yeh fields JSON response mein automatically aa jayengi:
        # id, name, email..., total_bookings_count, total_spent_amount

    def validate_phone(self, value):
        return validate_phone_number(value)

    def validate_email(self, value):
        request = self.context.get('request')
        hotel = getattr(request.user, 'hotel', None) if request else None

        qs = Customer.objects.filter(email=value, hotel=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A customer with this email already exists.")
        return value

    def get_total_bookings_count(self, obj):
        """
        Calculates total count of:
        1. Hotel Room Bookings (linked via User email or Guest email)
        2. Restaurant Table Reservations (linked via email)
        """
        email = obj.email
        if not email:
            return 0
        
        # Hotel filter add kiya taaki sirf usi hotel ki bookings count ho
        hotel_filter = Q()
        if obj.hotel:
            hotel_filter = Q(hotel=obj.hotel)

        #  Check Hotel Bookings (User who booked OR Guest listed in booking)
        # Q objects use karke hum User OR Guest dono mein email check kar rahe hain
        room_bookings = Booking.objects.filter(
            (Q(user__email=email) | Q(guests__email=email)) & hotel_filter
        ).distinct().count()

        # 2. Check Restaurant Activity
        # Note: RestaurantOrder model mein email nahi hai, isliye hum 
        # TableReservation use kar rahe hain jo email capture karta hai.
        restaurant_reservations = TableReservation.objects.filter(email=email).count()

        return room_bookings + restaurant_reservations

    def get_total_spent_amount(self, obj):
        """
        Calculates sum of 'amount_paid' from all Invoices issued to this user.
        """
        email = obj.email
        if not email:
            return 0

        # Billing App ke Invoice model se sum nikal rahe hain
        # Filter: Invoice jahan issued_to user ki email match kare
        total_spent = Invoice.objects.filter(
            issued_to__email=email
        ).aggregate(total=Sum('amount_paid'))['total']

        return total_spent if total_spent else 0


class InteractionSerializer(serializers.ModelSerializer):
    customer = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Customer.objects.all()
    )
    handled_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Interaction
        fields = '__all__'
        read_only_fields = ['hotel']

    def validate(self, data):
        method = data.get('method')
        date = data.get('date')
        
        # Method  Meetings cannot be in the past
        if method == 'meeting' and date < timezone.now():
             raise serializers.ValidationError({"date": "Meetings cannot be scheduled in the past."})

        # Method  Calls/Messages (Logs) cannot be in future
        if method in ['call', 'message'] and date > timezone.now():
             raise serializers.ValidationError({"date": "Call logs cannot be in the future."})

        return data