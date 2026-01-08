from django.contrib import admin
from .models import MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, DiscountRule, Restaurant, BookingCallback, RestaurantMedia

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state', 'country', 'email')
    search_fields = ('name', 'city', 'state', 'country')
    list_filter = ('city', 'state', 'country')

@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant')
    search_fields = ('name',)
    list_filter = ('restaurant',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('number', 'restaurant', 'capacity', 'status')
    list_filter = ('restaurant', 'status')
    search_fields = ('number',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    readonly_fields = ('slug',)
    fields = ('menu_item', 'quantity', 'price', 'slug')


@admin.register(RestaurantOrder)
class RestaurantOrderAdmin(admin.ModelAdmin):
    list_display = ('order_code', 'guest_name', 'guest_phone', 'restaurant', 'table', 'status', 'order_time', 'completed_at')
    list_filter = ('status', 'restaurant', 'order_time')
    search_fields = ('guest_name', 'guest_phone', 'slug')
    readonly_fields = ('slug', 'order_time', 'completed_at')
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Info', {
            'fields': ('slug', 'restaurant', 'table', 'guest_name', 'guest_phone', 'remarks', 'status')
        }),
        ('Timestamps', {
            'fields': ('order_time', 'completed_at'),
        }),
        ('Amount', {
            'fields': ('subtotal', 'sgst', 'cgst', 'discount','grand_total',),
        }),
    )

    def save_model(self, request, obj, form, change):
        """Ensure slug is auto-generated if not present."""
        if not obj.slug:
            obj.save()
        super().save_model(request, obj, form, change)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('slug', 'order', 'menu_item', 'quantity', 'price')
    list_filter = ('order__status', 'menu_item')
    search_fields = ('menu_item__name', 'order__slug')
    readonly_fields = ('slug',)

    fieldsets = (
        ('Order Item Info', {
            'fields': ('slug', 'order', 'menu_item', 'quantity', 'price')
        }),
    )

@admin.register(DiscountRule)
class DiscountRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'min_amount', 'max_amount', 'percentage', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('min_amount',)


@admin.register(BookingCallback)
class BookinCallbackAdmin(admin.ModelAdmin):
    list_display = ('restaurant_name',
    'phone_number',
    'preferred_time',
    'created_at',
    'is_resolved',)
    list_filter = ('is_resolved',)
    search_fields = ('restaurant_name',)


@admin.register(RestaurantMedia)
class RestaurantMediaAdmin(admin.ModelAdmin):
    list_display = (
        'restaurant',
        'media_type',
        'caption',
        'created_at',
    )

    list_filter = (
        'media_type',
        'created_at',
    )

    search_fields = (
        'restaurant__name',
        'caption',
    )

    readonly_fields = ('created_at',)

    ordering = ('-created_at',)