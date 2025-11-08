# billing/admin.py
from django.contrib import admin
from .models import Invoice, InvoiceItem, Payment


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ('amount',)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    readonly_fields = ('payment_date',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('slug', 'issued_to', 'issued_at', 'total_amount', 'status')
    search_fields = ('slug', 'issued_to__username')
    list_filter = ('status', 'issued_at')
    inlines = [InvoiceItemInline, PaymentInline]


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('description', 'invoice', 'quantity', 'unit_price', 'amount')
    search_fields = ('description', 'invoice__slug')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'invoice', 'amount_paid', 'method', 'payment_date')
    list_filter = ('method',)
    search_fields = ('invoice__slug', 'reference')
