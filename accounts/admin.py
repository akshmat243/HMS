from django.contrib import admin
# from .models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

User = get_user_model()

# Register your models here.
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ('email', 'full_name', 'role', 'is_active', 'created_by', 'date_joined')
    list_filter = ('is_active', 'role')
    readonly_fields = ('date_joined',)
    search_fields = ('email', 'full_name')

    fieldsets = (
        (None, {'fields': ('email', 'full_name', 'password')}),
        ('Permissions & Role', {'fields': ('is_active', 'is_staff', 'is_superuser', 'role')}),
        ('Audit Info', {'fields': ('created_by', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2', 'role', 'is_active')}
        ),
    )

    ordering = ('-date_joined',)
