from django.contrib import admin
from .models import Account, Transaction

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'opening_balance', 'is_active', 'created_at')
    list_filter = ('type', 'is_active')
    search_fields = ('name', 'slug')
    prepopulated_fields = {"slug": ("name",)}
    ordering = ('-created_at',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('account', 'type', 'amount', 'reference', 'date')
    list_filter = ('type', 'date')
    search_fields = ('account__name', 'reference', 'description')
    ordering = ('-date',)
