from django.contrib import admin
from .models import Lead, Customer, Interaction

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'source', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'assigned_to')
    search_fields = ('name', 'email', 'phone')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'loyalty_points', 'created_at')
    search_fields = ('name', 'email', 'phone')


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'method', 'date', 'handled_by')
    list_filter = ('method', 'date')
    search_fields = ('customer__name', 'handled_by__full_name')
