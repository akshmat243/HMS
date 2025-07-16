from django.contrib import admin
from .models import Account, Transaction

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'opening_balance', 'is_active', 'created_at')
    list_filter = ('type', 'is_active')
    search_fields = ('name',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('account', 'type', 'amount', 'date', 'reference')
    list_filter = ('type', 'date')
    search_fields = ('account__name', 'reference')
