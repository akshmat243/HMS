from django.contrib import admin
from .models import *

@admin.register(MaintenanceCategory)
class MaintenanceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel')
    search_fields = ('name', 'hotel__name')
    list_filter = ('hotel',)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel')
    search_fields = ('name', 'hotel__name')
    list_filter = ('hotel',)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel', 'serial_number')
    search_fields = ('name', 'serial_number')
    list_filter = ('hotel',)


@admin.register(MaintenanceTask)
class MaintenanceTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'location_type', 'slug', 'get_location', 'status', 'priority', 'assigned_to', 'created_at')
    search_fields = ('title', 'slug', 'room__room_number', 'facility__name', 'equipment__name', 'created_by__email')
    list_filter = ('status', 'priority', 'location_type')
    readonly_fields = ('slug', 'created_at', 'updated_at')

    def get_location(self, obj):
        return obj.get_location_display_name()
    get_location.short_description = 'Location'


@admin.register(RoomCleaningSchedule)
class RoomCleaningScheduleAdmin(admin.ModelAdmin):
    list_display = ('room', 'hotel', 'last_cleaned', 'next_cleaning')
    search_fields = ('room__room_number', 'hotel__name')



'''@admin.register(MaintenanceCategory)
class MaintenanceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel")
    list_filter = ("hotel",)
    search_fields = ("name",)


@admin.register(MaintenanceTask)
class MaintenanceTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title", "hotel", "room",
        "priority", "status",
        "assigned_to", "due_date", "created_by",
        "created_at"
    )
    list_filter = ("hotel", "status", "priority", "category")
    search_fields = ("title", "description")
    autocomplete_fields = ("room", "guest", "assigned_to", "category")
    ordering = ("-created_at",)


@admin.register(RoomCleaningSchedule)
class RoomCleaningScheduleAdmin(admin.ModelAdmin):
    list_display = ("room", "hotel", "last_cleaned", "next_cleaning")
    list_filter = ("hotel",)
    search_fields = ("room__room_number",)'''
