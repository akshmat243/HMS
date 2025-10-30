from rest_framework import serializers
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, Guest, RoomMedia


class HotelSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.full_name', read_only=True)
    
    class Meta:
        model = Hotel
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'updated_at', 'owner']

    def validate_name(self, value):
        qs = Hotel.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Hotel with this name already exists.")
        return value
    
    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['owner'] = user
        return super().create(validated_data)


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
        """Automatically assign hotel for admin users."""
        request = self.context.get('request')
        user = request.user

        if user.is_superuser:
            if 'hotel' not in data or data['hotel'] is None:
                raise serializers.ValidationError("Superuser must specify a hotel.")
        elif hasattr(user, 'role') and user.role == 'admin':
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
        if hasattr(obj, 'date_of_birth') and obj.date_of_birth:
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

    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['created_at', 'booking_code', 'slug', 'check_in_time', 'check_out_time']

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
        for guest in guests_data:
            Guest.objects.create(booking=booking, **guest)
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



class RoomServiceRequestSerializer(serializers.ModelSerializer):
    
    room = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Room.objects.all()
    )
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    
    class Meta:
        model = RoomServiceRequest
        fields = '__all__'
        read_only_fields = ['requested_at', 'slug']

    def validate(self, data):
        booking = data.get('booking', self.instance.booking if self.instance else None)
        user = data.get('user', self.instance.user if self.instance else None)
        room = data.get('room', self.instance.room if self.instance else None)
        service_type = data.get('service_type', self.instance.service_type if self.instance else None)

        # Optional: check if user matches booking
        if booking and user and hasattr(booking, 'user') and booking.user != user:
            raise serializers.ValidationError("This user is not associated with the selected booking.")

        if RoomServiceRequest.objects.filter(
            booking=booking,
            room=room,
            service_type=service_type,
            is_resolved=False
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A similar unresolved service request already exists for this room.")

        return data
