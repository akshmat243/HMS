from django.contrib import admin
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state', 'country', 'email')
    search_fields = ('name', 'city', 'state', 'country')
    list_filter = ('city', 'state', 'country')


@admin.register(RoomCategory)
class RoomCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel', 'price_per_night', 'max_occupancy')
    search_fields = ('name', 'hotel__name')
    list_filter = ('hotel',)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'hotel', 'room_category', 'floor', 'status', 'is_available')
    search_fields = ('room_number', 'hotel__name')
    list_filter = ('status', 'hotel')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('user', 'hotel', 'room', 'check_in', 'check_out', 'status', 'payment_status')
    list_filter = ('status', 'payment_status', 'hotel')
    search_fields = ('user__full_name', 'hotel__name', 'room__room_number')

@admin.register(RoomServiceRequest)
class RoomServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'service_type', 'requested_at', 'is_resolved')
    list_filter = ('service_type', 'is_resolved')
    search_fields = ('room__room_number', 'user__full_name', 'description')