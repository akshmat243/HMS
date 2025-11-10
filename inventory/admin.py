from django.contrib import admin
from .models import Supplier, InventoryCategory, InventoryItem, PurchaseOrder, PurchaseOrderItem


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'rating')
    search_fields = ('name', 'email', 'phone')
    list_filter = ('rating',)


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'supplier', 'stock_level', 'unit',
        'min_stock', 'max_stock', 'cost_per_unit', 'total_value', 'status'
    )
    search_fields = ('name', 'supplier__name')
    list_filter = ('status', 'category')
    list_editable = ('stock_level', 'cost_per_unit', 'total_value', 'status')


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'status', 'created_at')
    list_filter = ('status', 'supplier')
    search_fields = ('supplier__name',)
    date_hierarchy = 'created_at'


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'item', 'quantity', 'cost_per_unit', 'total_cost')
    search_fields = ('item__name', 'order__supplier__name')
