from django.contrib import admin
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, Guest, RoomMedia, Destination,MobileAppConfig,Package

class GuestInline(admin.TabularInline):
    model = Guest
    extra = 1
    fields = [
        'first_name', 'last_name', 'email', 'phone', 'gender',
        'id_proof_type', 'id_proof_number', 'special_request'
    ]
    readonly_fields = ['slug']
    show_change_link = True
    
    
@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state', 'country', 'email')
    search_fields = ('name', 'city', 'state', 'country')
    list_filter = ('city', 'state', 'country')


class RoomMediaInline(admin.TabularInline):
    model = RoomMedia
    extra = 1

@admin.register(RoomCategory)
class RoomCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel', 'price_per_night', 'max_occupancy')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'hotel', 'room_category', 'status', 'price_per_night')
    inlines = [RoomMediaInline]
    search_fields = ('room_number', 'room_code', 'hotel__name')
    list_filter = ('status', 'hotel', 'room_category')

admin.site.register(RoomMedia)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['booking_code', 'hotel', 'room', 'user', 'status', 'payment_status', 'check_in', 'check_out']
    list_filter = ['status', 'payment_status', 'hotel', 'room']
    search_fields = ['booking_code', 'user__full_name', 'hotel__name', 'room__room_number']
    inlines = [GuestInline]
    readonly_fields = ['booking_code', 'slug', 'created_at']
    ordering = ['-created_at']

@admin.register(RoomServiceRequest)
class RoomServiceRequestAdmin(admin.ModelAdmin):
    list_display = [
        'service_code', 'service_type', 'room', 'booking', 'user',
        'priority', 'status', 'cost', 'total_cost', 'requested_at', 'is_resolved'
    ]
    list_filter = [
        'service_type', 'priority', 'status', 'is_resolved', 'room__hotel'
    ]
    search_fields = [
        'service_code', 'room__room_number', 'user__full_name',
        'booking__id', 'slug'
    ]
    readonly_fields = [
        'service_code', 'slug', 'cost', 'base_cost', 'total_cost', 'requested_at'
    ]
    ordering = ['-requested_at']
    fieldsets = (
        (None, {
            'fields': (
                'service_code', 'slug', 'service_type', 'description', 'priority', 'status', 'is_resolved'
            )
        }),
        ('Related Info', {
            'fields': (
                'room', 'booking', 'user'
            )
        }),
        ('Cost Details', {
            'fields': (
                'base_cost', 'total_cost', 'cost'
            )
        }),
        ('Timing', {
            'fields': (
                'requested_at', 'pickup_time', 'delivery_time'
            )
        }),
    )

    
    
@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'booking', 'gender', 'phone', 'email']
    search_fields = ['first_name', 'last_name', 'email', 'phone', 'booking__booking_code']
    list_filter = ['gender']
    readonly_fields = ['slug']
    ordering = ['first_name']


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'image')   # admin list columns
    search_fields = ('name',)
    readonly_fields = ('slug',)  # slug & preview read-only
    # prepopulated_fields = {'slug': ('name',)}     # Auto-slug from name
    ordering = ('name',)

@admin.register(MobileAppConfig)
class MobileAppConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'updated_at')
    
    # Ye optional hai: Agar tu chahta hai admin panel me "Add" ka button
    # gayab ho jaye agar 1 object pehle se bana hua hai (Taaki sirf ek hi config rahe)
    def has_add_permission(self, request):
        # Agar pehle se koi object hai, to naya add mat karne do
        if MobileAppConfig.objects.exists():
            return False
        return True
    
@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'package_type', 'price')   # admin list columns
    search_fields = ('name','locations')
    readonly_fields = ('slug',)  # slug & preview read-only
    # prepopulated_fields = {'slug': ('name',)}     # Auto-slug from name
    ordering = ('name',)