from django.contrib import admin
from .models import HotelReview, RestaurantReview, ServiceReview

@admin.register(HotelReview)
class HotelReviewAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'user', 'rating', 'date')
    list_filter = ('rating', 'hotel')
    search_fields = ('hotel__name', 'user__full_name')


@admin.register(RestaurantReview)
class RestaurantReviewAdmin(admin.ModelAdmin):
    list_display = ('menu_item', 'user', 'rating', 'date')
    list_filter = ('rating',)
    search_fields = ('menu_item__name', 'user__full_name')


@admin.register(ServiceReview)
class ServiceReviewAdmin(admin.ModelAdmin):
    list_display = ('service_type', 'user', 'rating', 'date')
    list_filter = ('service_type', 'rating')
    search_fields = ('user__full_name', 'service_type')
