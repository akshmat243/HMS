from rest_framework import serializers
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, Guest, RoomMedia
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

        hotel = Hotel.objects.create(owner=owner, **validated_data)
        return hotel

    def update(self, instance, validated_data):
        # Prevent changing owner except by superuser
        if 'owner_slug' in validated_data:
            request = self.context['request']
            if not request.user.is_superuser:
                raise serializers.ValidationError({'owner_slug': 'You cannot change hotel admin.'})
            owner_slug = validated_data.pop('owner_slug')
            instance.owner = User.objects.get(slug=owner_slug)

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

    class Meta:
        model = Room
        fields = [
            'id', 'hotel_slug', 'room_category', 'room_number', 'room_code', 'slug',
            'floor', 'is_available', 'status', 'price_per_night', 'amenities',
            'bed_type', 'room_size', 'view', 'description', 'media'
        ]
        read_only_fields = ['slug']

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
        if hasattr(user, 'role') and user.role == 'admin':
            validated_data['hotel'] = getattr(user, 'hotel', None)

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
        exclude = ['booking']  # or: read_only_fields = ['booking']
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
    guests = GuestSerializer(many=True, required=True)
    room_number = serializers.CharField(source="room.room_number", read_only=True)

    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['created_at', 'booking_code', 'slug', 'check_in_time', 'check_out_time', 'room_number']

    def validate(self, data):
        check_in = data.get('check_in', self.instance.check_in if self.instance else None)
        check_out = data.get('check_out', self.instance.check_out if self.instance else None)
        room = data.get('room', self.instance.room if self.instance else None)

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
        guests_data = validated_data.pop('guests', [])
        booking = Booking.objects.create(**validated_data)
        room = booking.room
        room.is_available = False
        room.save(update_fields=['is_available'])
        for guest in guests_data:
            Guest.objects.create(booking=booking, **guest)
            
        # ✅ Auto-generate invoice for this booking
        content_type = ContentType.objects.get_for_model(Booking)
        invoice = Invoice.objects.create(
            content_type=content_type,
            object_id=booking.id,
            issued_to=booking.user,
            total_amount=booking.room.price_per_night,
            status='unpaid'
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f"Room Booking - {booking.room.room_number}",
            quantity=1,
            unit_price=booking.room.price_per_night
        )
        
        return booking

    def update(self, instance, validated_data):
        guests_data = validated_data.pop('guests', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

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
            'requested_at', 'pickup_time', 'delivery_time', 'is_resolved',
        ]
        read_only_fields = [
            'id', 'service_code', 'slug', 'status_display', 'priority_display', 'service_type_display',
            'base_cost', 'cost', 'total_cost', 'room_number', 'hotel_name', 'user_name', 'requested_at',
            'booking_slug', 'room_slug'
        ]

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
