from rest_framework import serializers
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest


class HotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = '__all__'
        read_only_fields = ['slug']

    def validate_name(self, value):
        qs = Hotel.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Hotel with this name already exists.")
        return value


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


class RoomSerializer(serializers.ModelSerializer):
    
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )
    room_category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=RoomCategory.objects.all(),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = Room
        fields = '__all__'
        read_only_fields = ['slug']

    def validate(self, data):
        hotel = data.get('hotel', self.instance.hotel if self.instance else None)
        number = data.get('room_number', self.instance.room_number if self.instance else None)

        qs = Room.objects.filter(hotel=hotel, room_number=number)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This room number already exists in the hotel.")
        return data


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
    
    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        room = data.get('room', self.instance.room if self.instance else None)
        check_in = data.get('check_in', self.instance.check_in if self.instance else None)
        check_out = data.get('check_out', self.instance.check_out if self.instance else None)

        if check_in and check_out and check_in >= check_out:
            raise serializers.ValidationError("Check-out must be after check-in.")

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
