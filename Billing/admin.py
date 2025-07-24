from django.contrib import admin
from .models import Invoice, InvoiceItem, Payment

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('slug', 'booking', 'issued_to', 'total_amount', 'status', 'issued_at', 'due_date')
    list_filter = ('status', 'due_date', 'issued_at')
    search_fields = ('slug', 'booking__id', 'issued_to__full_name', 'notes')
    inlines = [InvoiceItemInline, PaymentInline]
    readonly_fields = ('slug', 'issued_at')
    ordering = ('-issued_at',)


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'description', 'amount')
    search_fields = ('invoice__slug', 'description')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount_paid', 'payment_date', 'method', 'reference')
    list_filter = ('method', 'payment_date')
    search_fields = ('invoice__slug', 'reference')
