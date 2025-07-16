from django.contrib import admin
from .models import LaundryService, LaundryOrder

@admin.register(LaundryService)
class LaundryServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'rate', 'rate_type', 'estimated_time')
    search_fields = ('name',)
    list_filter = ('rate_type',)


@admin.register(LaundryOrder)
class LaundryOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'room', 'service', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__full_name', 'room__room_number')
