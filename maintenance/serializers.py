from rest_framework import serializers
from .models import *
from Hotel.models import Room, Guest



class MaintenanceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceCategory
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'hotel']


class MaintenanceTaskSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    guest_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)

    class Meta:
        model = MaintenanceTask
        fields = [
            'slug', 'hotel','hotel_name', 'category','category_name', 'room_number',
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


class RoomCleaningScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomCleaningSchedule
        fields = "__all__"
        read_only_fields = ["hotel", "room"]
