from django.contrib import admin
from .models import (
    MaintenanceTask,
    MaintenanceCategory,
    RoomCleaningSchedule
)

@admin.register(MaintenanceCategory)
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
    search_fields = ("room__room_number",)
