from django.contrib import admin
from .models import Invoice, Payment

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'customer', 'final_amount', 'status', 'invoice_date', 'due_date')
    list_filter = ('status', 'invoice_date')
    search_fields = ('booking__id', 'customer__name')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'method', 'amount', 'payment_date')
    list_filter = ('method', 'payment_date')
    search_fields = ('reference_number',)
