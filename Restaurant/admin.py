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


@admin.register(RestaurantOrder)
class RestaurantOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'table', 'total_amount', 'status', 'order_time')
    list_filter = ('status', 'order_time')
    search_fields = ('user__full_name', 'table__number')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'menu_item', 'quantity', 'price')
    search_fields = ('menu_item__name',)
