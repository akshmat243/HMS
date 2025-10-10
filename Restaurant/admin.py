from django.contrib import admin
from .models import MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem

@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'hotel')
    search_fields = ('name',)
    list_filter = ('hotel',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('number', 'hotel', 'capacity', 'status')
    list_filter = ('hotel', 'status')
    search_fields = ('number',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    readonly_fields = ('slug',)
    fields = ('menu_item', 'quantity', 'price', 'slug')


@admin.register(RestaurantOrder)
class RestaurantOrderAdmin(admin.ModelAdmin):
    list_display = ('slug', 'guest_name', 'guest_phone', 'hotel', 'table', 'status', 'order_time', 'completed_at')
    list_filter = ('status', 'hotel', 'order_time')
    search_fields = ('guest_name', 'guest_phone', 'slug')
    readonly_fields = ('slug', 'order_time', 'completed_at')
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Info', {
            'fields': ('slug', 'hotel', 'table', 'guest_name', 'guest_phone', 'remarks', 'status')
        }),
        ('Timestamps', {
            'fields': ('order_time', 'completed_at'),
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
