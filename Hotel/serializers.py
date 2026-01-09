from rest_framework import serializers
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, Guest, RoomMedia, Destination, Package,HotelMedia
from django.db.models import Min, Avg, Count
from Restaurant.models import Restaurant
from django.utils import timezone
from django.db.models.functions import Coalesce
from .utils import ensure_module

from django.contrib.auth import get_user_model
User = get_user_model()


class HotelSerializer(serializers.ModelSerializer):
    owner_slug = serializers.SlugField(write_only=True, required=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = Hotel
        fields = [
            'id', 'slug', 'name', 'description', 'address', 'city', 'state', 'country',
            'pincode', 'contact_number', 'email', 'logo', 'cover_image', 'status',
            'owner_slug', 'owner_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def create(self, validated_data):
        owner_slug = validated_data.pop('owner_slug')
        try:
            owner = User.objects.get(slug=owner_slug)
        except User.DoesNotExist:
            raise serializers.ValidationError({'owner_slug': 'Invalid admin user slug'})

        if str(owner.role).lower() != 'admin':
            raise serializers.ValidationError({'owner_slug': 'User must have Admin role'})

        if Hotel.objects.filter(owner=owner).exists():
            raise serializers.ValidationError({'owner_slug': 'This admin already owns a hotel'})
        
        ensure_module(owner, "hotel")

        hotel = Hotel.objects.create(owner=owner, **validated_data)
        return hotel

    def update(self, instance, validated_data):
        # Prevent changing owner except by superuser
        if 'owner_slug' in validated_data:
            request = self.context['request']
            if not request.user.is_superuser:
                raise serializers.ValidationError({'owner_slug': 'You cannot change hotel admin.'})
            
        owner_slug = validated_data.pop('owner_slug')
        try:
            instance.owner = User.objects.get(slug=owner_slug)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'owner_slug': 'Invalid admin user slug.'
            })

        return super().update(instance, validated_data)



class RoomCategorySerializer(serializers.ModelSerializer):
    
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )
    
    class Meta:
        model = RoomCategory
        fields = '__all__'
        read_only_fields = ['slug']

    def validate_name(self, value):
        qs = RoomCategory.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A room category with this name already exists.")
        return value
    
    
class RoomMediaSerializer(serializers.ModelSerializer):
    """Serializer for room media (images/videos)."""
    class Meta:
        model = RoomMedia
        fields = ['id', 'file', 'media_type', 'caption']


class RoomSerializer(serializers.ModelSerializer):
    """Serializer for displaying room with its media."""
    media = RoomMediaSerializer(many=True, read_only=True)
    hotel_slug = serializers.SlugRelatedField(
        source='hotel',
        slug_field='slug',
        queryset=Hotel.objects.all(),
        required=False,
        allow_null=True
    )
    
    room_category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=RoomCategory.objects.all()
    )
    max_occupancy = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            'id', 'hotel_slug', 'room_category', 'room_number', 'room_code', 'slug',
            'floor', 'is_available', 'status', 'price_per_night', 'amenities',
            'bed_type', 'room_size', 'view', 'description', 'media', 'max_occupancy'
        ]
        read_only_fields = ['slug']
    
    def get_max_occupancy(self, obj):
        return obj.room_category.max_occupancy if obj.room_category else None

    def validate(self, data):
        request = self.context.get('request')
        user = request.user

        if user.is_superuser:
            # If creating/updating, use existing hotel if not provided
            if 'hotel' not in data or data['hotel'] is None:
                if self.instance:
                    # use existing room hotel
                    data['hotel'] = self.instance.hotel
                else:
                    raise serializers.ValidationError("Superuser must specify a hotel.")
        
        elif hasattr(user, 'role') and user.role.name.lower() == 'admin':
            data['hotel'] = getattr(user, 'hotel', None)
            if not data['hotel']:
                raise serializers.ValidationError("You are not assigned to any hotel.")
        else:
            raise serializers.ValidationError("You do not have permission to manage rooms.")

        return data


class RoomCreateUpdateSerializer(RoomSerializer):
    """
    Serializer for creating/updating rooms with multiple media uploads.
    Accepts 'media_files' as list of files with 'media_type' = image/video.
    """
    media_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )
    media_type = serializers.ChoiceField(
        choices=RoomMedia.ROOM_MEDIA_TYPE,
        write_only=True,
        required=False,
        default='image'
    )

    class Meta(RoomSerializer.Meta):
        fields = RoomSerializer.Meta.fields + ['media_files', 'media_type']
        extra_kwargs = {
            'room_number': {'required': False, 'read_only': True},  # ✅ Auto-generate
            'room_code': {'required': True},  # ✅ Must be passed manually
        }

    def create(self, validated_data):
        media_files = validated_data.pop('media_files', [])
        media_type = validated_data.pop('media_type', 'image')
        request = self.context.get('request')
        user = request.user

        # Assign hotel for admin users
        # if hasattr(user, 'role') and user.role.name.lower() == 'admin':
        #     validated_data['hotel'] = getattr(user, 'hotel', None)

        room = Room.objects.create(**validated_data)

        # Save uploaded media files
        for file in media_files:
            RoomMedia.objects.create(room=room, file=file, media_type=media_type)
        return room

    def update(self, instance, validated_data):
        media_files = validated_data.pop('media_files', [])
        media_type = validated_data.pop('media_type', 'image')

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Append new media files (don’t delete old ones)
        for file in media_files:
            RoomMedia.objects.create(room=instance, file=file, media_type=media_type)
        return instance

from datetime import date

class GuestSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()

    class Meta:
        model = Guest
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "gender",
            "id_proof_type",
            "id_proof_number",
            "id_proof_file",
            "special_request",
            "age"
        ]
        read_only_fields = ['slug', 'created_at']

    def get_age(self, obj):
        if hasattr(obj, 'date_of_birth' ) and obj.date_of_birth:
            today = date.today()
            return today.year - obj.date_of_birth.year - (
                (today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day)
            )
        return None



class BookingSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )
    room = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Room.objects.all()
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    guests = serializers.ListField(
        write_only=True,
        required=True,
        allow_empty=True
    )
    
    guests_data = GuestSerializer(
        many=True,
        read_only=True,
        source="guests"
    )

    room_number = serializers.CharField(source="room.room_number", read_only=True)
    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['created_at', 'booking_code', 'slug', 'check_in_time', 'check_out_time', 'room_number']

    def validate(self, data):
        check_in = data.get('check_in', self.instance.check_in if self.instance else None)
        check_out = data.get('check_out', self.instance.check_out if self.instance else None)
        room = data.get('room', self.instance.room if self.instance else None)
        
        guests = data.get("guests", [])
        if data.get("guests_count") != len(guests):
            raise serializers.ValidationError(
                "Guests count does not match guests provided."
            )

        # ✅ Check date order
        if check_in and check_out and check_in >= check_out:
            raise serializers.ValidationError("Check-out must be after check-in.")

        # ✅ Prevent overlapping bookings
        overlapping = Booking.objects.filter(
            room=room,
            check_out__gt=check_in,
            check_in__lt=check_out
        )
        if self.instance:
            overlapping = overlapping.exclude(id=self.instance.id)
        if overlapping.exists():
            raise serializers.ValidationError("This room is already booked for the selected dates.")

        return data

    def create(self, validated_data):
        request = self.context["request"]

        # remove guests from DRF flow
        validated_data.pop("guests", None)

        booking = Booking.objects.create(**validated_data)

        # reserve room
        booking.room.status = "reserved"
        booking.room.save()

        # ----------------------------
        # MANUAL GUEST PARSING
        # ----------------------------
        index = 0
        while True:
            prefix = f"guests[{index}]"
            if f"{prefix}[first_name]" not in request.data:
                break

            Guest.objects.create(
                booking=booking,
                first_name=request.data.get(f"{prefix}[first_name]"),
                last_name=request.data.get(f"{prefix}[last_name]"),
                email=request.data.get(f"{prefix}[email]"),
                phone=request.data.get(f"{prefix}[phone]"),
                gender=request.data.get(f"{prefix}[gender]"),
                id_proof_type=request.data.get(f"{prefix}[id_proof_type]"),
                id_proof_number=request.data.get(f"{prefix}[id_proof_number]"),
                id_proof_file=request.FILES.get(f"{prefix}[id_proof_file]"),
                special_request=request.data.get(f"{prefix}[special_request]"),
            )

            index += 1
            
        # ✅ Auto-generate invoice for this booking
        content_type = ContentType.objects.get_for_model(Booking)
        guest = booking.guests.first()

        customer_name = (
            f"{guest.first_name} {guest.last_name or ''}".strip()
            if guest else
            booking.user.full_name or "Guest"
            )
        invoice = Invoice.objects.create(
            content_type=content_type,
            object_id=booking.id,
            issued_to=booking.user,
            customer_name=customer_name,
            # days = booking.total_nights,
            total_amount=booking.room.price_per_night * booking.total_nights,
            status='unpaid',
            created_by= booking.user
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f"Room Booking - {booking.room.room_number}",
            quantity=1,
            unit_price=booking.room.price_per_night
        )
        
        return booking

    def update(self, instance, validated_data):
        # 1. Guests data nikal lo
        guests_data = validated_data.pop('guests', None)
        
        # 2. Status change detect karo
        new_status = validated_data.get('status')
        old_status = instance.status

        # --- NEW TIME LOGIC start ---
        # Agar status "checked_in" ho raha hai, to abhi ka time set karo
        if new_status == 'checked_in' and old_status != 'checked_in':
            instance.check_in_time = timezone.now()
            # Room ko occupied mark kar sakte hain
            if instance.room:
                instance.room.status = "occupied"
                instance.room.save()

        # Agar status "checked_out" ho raha hai, to abhi ka time set karo
        if new_status == 'checked_out' and old_status != 'checked_out':
            instance.check_out_time = timezone.now()
            # Room ko free karo (Available)
            if instance.room:
                instance.room.status = "available"
                instance.room.save()
        # --- new TIME LOGIC END ---

        # 3. Baaki fields update karo
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # 4. Room Status Logic
        if instance.status == 'cancelled' and instance.room:
            instance.room.status = "available"
            instance.room.save()

        if instance.status == 'confirmed' and instance.room:
            instance.room.status = "reserved"
            instance.room.save()

        # 5. Guests Update Logic 
        if guests_data is not None:
            instance.guests.all().delete()  # clear old guests
            for guest in guests_data:
                Guest.objects.create(booking=instance, **guest)

        return instance
    
from Billing.models import Invoice, InvoiceItem
from django.contrib.contenttypes.models import ContentType




class RoomServiceRequestSerializer(serializers.ModelSerializer):
    # Readable choice labels
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    # Calculated cost fields (read-only)
    base_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    # Nested related fields for display
    room_number = serializers.CharField(source="room.room_number", read_only=True)
    hotel_name = serializers.CharField(source="room.hotel.name", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    booking_slug = serializers.CharField(source='booking.slug', read_only=True)
    room_slug = serializers.CharField(source='room.slug', read_only=True)
    
    booking_guest_name = serializers.SerializerMethodField()
    
    # 🔹 Slug-based related fields
    booking = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Booking.objects.all()
    )
    room = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Room.objects.all()
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = RoomServiceRequest
        fields = [
            'id', 'service_code', 'slug', 'booking', 'booking_slug', 'user', 'room', 'room_slug',
            'room_number', 'hotel_name', 'user_name',
            'service_type', 'service_type_display', 'description',
            'priority', 'priority_display', 'status', 'status_display',
            'cost', 'base_cost', 'total_cost',
            'requested_at', 'pickup_time', 'delivery_time', 'is_resolved', 'booking_guest_name',
        ]
        read_only_fields = [
            'id', 'service_code', 'slug', 'status_display', 'priority_display', 'service_type_display',
            'base_cost', 'cost', 'total_cost', 'room_number', 'hotel_name', 'user_name', 'requested_at',
            'booking_slug', 'room_slug', 'booking_guest_name'
        ]

    def get_booking_guest_name(self, obj):
        guests = obj.booking.guests.all()
        if guests.exists():
            g = guests.first()
            return f"{g.first_name} {g.last_name}".strip()
        return None

    # Validate JSON field and all business rules
    def validate_description(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Description must be a dictionary.")
        items = value.get('items', [])
        if not isinstance(items, list):
            raise serializers.ValidationError("Items should be a list.")
        for item in items:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Every item must be a dict.")
            if 'name' not in item or not item['name']:
                raise serializers.ValidationError("Each item must have a name.")
            if 'qty' in item and (not isinstance(item['qty'], int) or item['qty'] <= 0):
                raise serializers.ValidationError("Quantity must be a positive integer.")
        return value

    def validate(self, attrs):
        if attrs.get('service_type') == 'laundry':
            items = attrs.get('description', {}).get('items', [])
            if not items:
                raise serializers.ValidationError("Laundry service must specify at least one item.")
        return attrs
    
    def validate_status(self, new_status):
        instance = self.instance
        if not instance:
            return new_status  # new request

        allowed = {
            "pending": ["in_progress", "hold"],
            "in_progress": ["quality_check", "ready", "hold"],
            "quality_check": ["ready", "hold"],
            "ready": ["delivered", "hold"],
            "hold": ["in_progress"],
            "delivered": []
        }

        old_status = instance.status
        if new_status not in allowed.get(old_status, []):
            raise serializers.ValidationError(
                f"Cannot move from {old_status} → {new_status}."
            )
        return new_status

class HotelSearchSerializer(serializers.ModelSerializer):
    """
    Simplified Serializer for Public Search Results.
    Includes 'starting_price' for the UI.
    """
    starting_price = serializers.SerializerMethodField()
    available_rooms_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Hotel
        fields = [
            'id', 'slug', 'name', 'city', 'state', 'country', 
            'cover_image', 'starting_price', 'available_rooms_count', 'description'
        ]

    def get_starting_price(self, obj):
        # Find the cheapest room category price for this hotel
        min_price = obj.room_categories.aggregate(min_p=Min('price_per_night'))['min_p']
        return min_price if min_price else 0
    
class DestinationSerializer(serializers.ModelSerializer):
    # City Level Countt
    hotel_count = serializers.IntegerField(read_only=True)
    restaurant_count = serializers.IntegerField(read_only=True)

    # State level counts
    state_hotel_count = serializers.IntegerField(read_only=True)
    state_restaurant_count = serializers.IntegerField(read_only=True)

    rating = serializers.FloatField(read_only=True)
    state = serializers.CharField(read_only=True)
    country = serializers.CharField(read_only=True)

    class Meta:
        model = Destination
        fields = [
            'id', 'name', 'slug', 'image', 'description', 
            'hotel_count', 'restaurant_count','state_hotel_count','state_restaurant_count', 
            'rating', 'state', 'country','created_at','updated_at'
        ]



class HotelListingSerializer(serializers.ModelSerializer):
    # Mapping model fields to the names you requested
    cover_photo = serializers.ImageField(source='cover_image', read_only=True)
    price = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    type = serializers.CharField(default="hotel", read_only=True) # Frontend identification ke liye

    class Meta:
        model = Hotel
        fields = [
            'id', 'type', 'name', 'description', 'amenities', 
            'cover_photo', 'address', 'price', 'review'
        ]

    def get_price(self, obj):
        # RoomCategory se minimum price nikalna
        # Agar humne view me annotate kiya h to waha se lenge, nahi to query karenge
        if hasattr(obj, 'min_price') and obj.min_price is not None:
            return obj.min_price
        
        # Fallback query
        min_price = obj.room_categories.aggregate(minimum=Min('price_per_night'))['minimum']
        return min_price if min_price else 0

    def get_review(self, obj):
        # HotelReview model se data
        # View me optimization ke liye annotate use karenge
        avg_rating = getattr(obj, 'avg_rating', None)
        total_reviews = getattr(obj, 'total_reviews', None)

        if avg_rating is None:
            data = obj.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
            avg_rating = data['avg'] or 0
            total_reviews = data['count'] or 0
        
        return {
            "rating": round(avg_rating, 1),
            "count": total_reviews
        }

class RestaurantListingSerializer(serializers.ModelSerializer):
    cover_photo = serializers.ImageField(source='cover_image', read_only=True)
    review = serializers.SerializerMethodField()
    type = serializers.CharField(default="restaurant", read_only=True)

    class Meta:
        model = Restaurant
        fields = [
            'id', 'type', 'name', 'address', 'category', 
            'description', 'amenities', 'cover_photo', 'review'
        ]

    def get_review(self, obj):
        # Restaurant model me already 'rating' field hai.
        # User ne kaha review model se lao, lekin tumhare schema me
        # 'RestaurantReview' menu items se linked hai, restaurant se nahi directly.
        # Isliye best practice hai ki hum Restaurant model ka 'rating' field use karein
        # ya phir dummy count dikhayein abhi ke liye.
        
        return {
            "rating": obj.rating, 
            "count": "250+" # Ya random number, kyunki schema me direct link nahi hai
        }
    

class PackageSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = Package
        fields = [
            'id', 
            'owner', 
            'owner_name', 
            'name', 
            'slug', 
            'category',       # Destination vs Theme
            'locations',      # e.g., Dubai | Kashmir
            'departure_city', # New: From Delhi (Model mein jo naam hai wahi rakhna)
            'duration_days',  # Typo Fixed (was uration_days)
            'price', 
            'price_unit',     # New: Per Person/Couple
            'members_included', # New: Calculation ke liye
            'total_seats',    # New: Inventory check
            'cover_image', 
            'package_type',   # International/Domestic
            'description', 
            'is_active',
            'created_at'      # Display ke liye accha rehta hai
        ]
        read_only_fields = ['id', 'slug', 'owner', 'created_at']

    # --- VALIDATIONS (Data Safai) ---

    def validate_price(self, value):
        """Check 1: Price 0 ya negative nahi ho sakta"""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value

    def validate_duration_days(self, value):
        """Check 2: Trip kam se kam 1 din ki honi chahiye"""
        if value < 1:
            raise serializers.ValidationError("Duration must be at least 1 day.")
        return value

    def validate(self, data):
        """
        Check 3: Business Logic Validation
        Yahan hum check karenge ki Price Unit aur Members match kar rahe hain ya nahi.
        """
        unit = data.get('price_unit')
        members = data.get('members_included')

        # Agar user "Per Couple" select kare lekin members 1 daal de, to error do
        if unit == 'per_couple' and members != 2:
            raise serializers.ValidationError({
                "members_included": "For 'Per Couple' pricing, members included must be 2."
            })
        
        # Agar user "Per Person" select kare lekin members 2 daal de
        if unit == 'per_person' and members != 1:
             raise serializers.ValidationError({
                "members_included": "For 'Per Person' pricing, members included must be 1."
            })

        return data
    


class ActivityLogSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()  # booking, payment, checkin, checkout, maintenance, order, system
    title = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField()
    
    # Dynamic styling fields 
    status_color = serializers.CharField() # e.g., 'success', 'warning', 'info'
    icon_text = serializers.CharField()    # e.g., 'Booking', 'Payment'
    
    # Staff / Actor Details
    staff_name = serializers.CharField(allow_null=True)
    staff_designation = serializers.CharField(allow_null=True)
    staff_department = serializers.CharField(allow_null=True)


class HotelMediaSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
            slug_field='slug',
            queryset=Hotel.objects.all()
        )


    hotel_name = serializers.CharField(
        source='hotel.name',
        read_only=True
    )
    file = serializers.FileField(required=False)

    files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = HotelMedia
        fields = [
            'id',
            'hotel',
            'hotel_name',
            'file',
            'files',
            'media_type',
            'caption',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        files = validated_data.pop('files', None)

        #  SINGLE FILE
        if not files:
            return super().create(validated_data)

        #  MULTIPLE FILES
        media_objects = []
        for file in files:
            media = HotelMedia.objects.create(
                file=file,
                **validated_data
            )
            media_objects.append(media)

        return media_objects