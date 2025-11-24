# events/admin.py
from django.contrib import admin
from .models import Venue, Event, EventType, Event_Booking as Booking

@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "capacity", "hourly_rate", "is_active", "created_by")
    search_fields = ("name",)
    readonly_fields = ("created_at",)

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "venue", "start_datetime", "end_datetime", "status", "created_by")
    list_filter = ("status", "event_type")
    search_fields = ("title", "description", "tags")

admin.site.register(EventType)
admin.site.register(Booking)
