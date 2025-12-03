from rest_framework import serializers
from .models import *
from Hotel.models import Room, Guest
from django.contrib.auth import get_user_model
User = get_user_model()


class MaintenanceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceCategory
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'hotel']


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ['id', 'slug', 'hotel', 'name', 'description']
        read_only_fields = ['id', 'slug', 'hotel']


class EquipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Equipment
        fields = ['id', 'slug', 'hotel', 'name', 'serial_number', 'description']
        read_only_fields = ['id', 'slug', 'hotel']


class MaintenanceTaskSerializer(serializers.ModelSerializer):
    # Accept PKs (UUIDs) on write; return friendly fields on read
    # room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)
    # facility = serializers.PrimaryKeyRelatedField(queryset=Facility.objects.all(), required=False, allow_null=True)
    # equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all(), required=False, allow_null=True)

    # Accept & return SLUGS instead of UUIDs
    category = serializers.SlugRelatedField(slug_field='slug',queryset=MaintenanceCategory.objects.all())
    room = serializers.SlugRelatedField(slug_field='slug',queryset=Room.objects.all(),required=False,allow_null=True)
    guest = serializers.SlugRelatedField(slug_field='slug',queryset=Guest.objects.all(),required=False,allow_null=True)
    facility = serializers.SlugRelatedField(slug_field='slug',queryset=Facility.objects.all(),required=False,allow_null=True)
    equipment = serializers.SlugRelatedField(slug_field='slug',queryset=Equipment.objects.all(),required=False,allow_null=True)
    assigned_to = serializers.SlugRelatedField(slug_field='slug',queryset=User.objects.all(),required=False,allow_null=True)

    room_number = serializers.CharField(source='room.room_number', read_only=True)
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)
    location_name = serializers.SerializerMethodField()

    guest_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    icon_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = MaintenanceTask
        fields = [
            'id', 'slug',
            'hotel', 'hotel_name',
            'category', 'category_name',
            'icon_name',

            'location_type', 'room', 'room_number',
            'facility', 'facility_name', 'equipment', 'equipment_name',
            'location_note', 'location_name',

            'guest', 'guest_name',
            'title', 'description',
            'priority', 'status',
            'assigned_to', 'assigned_to_name',
            'due_date', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'hotel', 'created_by', 'created_at', 'updated_at',
                            'hotel_name', 'created_by_name', 'room_number',
                            'facility_name', 'equipment_name', 'location_name', 'category_name']

    def get_guest_name(self, obj):
        if obj.guest:
            return f"{obj.guest.first_name} {obj.guest.last_name or ''}".strip()
        return None

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.full_name if obj.assigned_to else None

    def get_location_name(self, obj):
        return obj.get_location_display_name()

    def validate(self, data):
        """
        Validate that the provided location matches the location_type and belongs to the same hotel.
        Also ensure admin user has hotel assigned.
        """
        user = self.context['request'].user

        # Ensure admin has hotel
        if not getattr(user, "hotel", None):
            raise serializers.ValidationError("Your account is not linked to any hotel.")

        # Hotel set by server (ignore any incoming hotel)
        data['hotel'] = user.hotel

        location_type = data.get('location_type', getattr(self.instance, 'location_type', None))

        # When creating/updating ensure appropriate field present based on location_type
        if location_type == 'room':
            room = data.get('room', getattr(self.instance, 'room', None))
            if not room:
                raise serializers.ValidationError({"room": "Room is required for location_type 'room'."})
            # Check belongs to same hotel
            if getattr(room, 'hotel', None) != user.hotel:
                raise serializers.ValidationError({"room": "Room does not belong to your hotel."})

            # clear other location fields
            data['facility'] = None
            data['equipment'] = None

        elif location_type == 'facility':
            facility = data.get('facility', getattr(self.instance, 'facility', None))
            if not facility:
                raise serializers.ValidationError({"facility": "Facility is required for location_type 'facility'."})
            if getattr(facility, 'hotel', None) != user.hotel:
                raise serializers.ValidationError({"facility": "Facility does not belong to your hotel."})
            data['room'] = None
            data['equipment'] = None

        elif location_type == 'equipment':
            equipment = data.get('equipment', getattr(self.instance, 'equipment', None))
            if not equipment:
                raise serializers.ValidationError({"equipment": "Equipment is required for location_type 'equipment'."})
            if getattr(equipment, 'hotel', None) != user.hotel:
                raise serializers.ValidationError({"equipment": "Equipment does not belong to your hotel."})
            data['room'] = None
            data['facility'] = None

        else:
            # if location_type missing, default to room-based for backward compatibility
            if not getattr(self.instance, 'location_type', None):
                raise serializers.ValidationError({"location_type": "Invalid or missing location_type."})

        return data

    def create(self, validated_data):
        user = self.context['request'].user
        # hotel already set in validate()
        validated_data['created_by'] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # ensure hotel remains same
        validated_data['hotel'] = instance.hotel
        return super().update(instance, validated_data)


'''class MaintenanceTaskSerializer(serializers.ModelSerializer):
    room = serializers.PrimaryKeyRelatedField(
    queryset=Room.objects.all()
    )
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    guest_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)

    class Meta:
        model = MaintenanceTask
        fields = [
            'slug', 'hotel','hotel_name', 'category','category_name','room', 'room_number',
            'guest_name', 'title', 'description',
            'priority', 'status', 'assigned_to', 'assigned_to_name',
            'due_date', 'created_by','created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'hotel', 'created_by', 'created_at', 'updated_at','hotel_name','created_by_name']

    def get_guest_name(self, obj):
        if obj.guest:
            return f"{obj.guest.first_name} {obj.guest.last_name or ''}".strip()
        return None

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.full_name if obj.assigned_to else None

    def validate(self, data):
        room = data.get("room")
        user = self.context['request'].user
        print(room,user)

        if room.hotel != user.hotel:
            raise serializers.ValidationError("Room does not belong to your hotel.")

        return data

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['hotel'] = user.hotel
        validated_data['created_by'] = user
        return super().create(validated_data)
'''


class RoomCleaningScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomCleaningSchedule
        fields = "__all__"
        read_only_fields = ["hotel", "room"]
