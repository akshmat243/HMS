from django.contrib import admin
from .models import *


# ================================
# 1. Service Category Admin
# ================================
@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


# ================================
# 2. Guest Service Admin
# ================================
@admin.register(GuestService)
class GuestServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "price",
        "duration_minutes",
        "status",
        "rating",
        "total_bookings",
        "created_at",
    )
    list_filter = ("status", "category")
    search_fields = ("name", "slug", "category__name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    prepopulated_fields = {"slug": ("name",)}


# ================================
# 3. Service Request Admin
# ================================
@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "service_type",
        "category",
        "guest_name",
        "guest_room",
        "status",
        "priority",
        "cost",
        "rating",
        "assigned_to",
        "created_at",
    )
    list_filter = ("status", "priority", "category")
    search_fields = (
        "service_type",
        "category",
        "guest_name",
        "guest_room",
        "booking__booking_code",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
