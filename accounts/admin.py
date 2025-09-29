from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from accounts.models import Profile
from django.contrib.auth import get_user_model

User = get_user_model()

# Register your models here.
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ('email', 'full_name', 'slug', 'role', 'is_active', 'created_by', 'date_joined')
    list_filter = ('is_active', 'role')
    readonly_fields = ('date_joined', 'slug')
    search_fields = ('email', 'slug', 'full_name')

    fieldsets = (
        (None, {'fields': ('email', 'phone', 'full_name', 'password')}),
        ('Permissions & Role', {'fields': ('is_active', 'is_staff', 'is_superuser', 'role', 'is_email_verified', 'is_phone_verified')}),
        ('Audit Info', {'fields': ('created_by', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2', 'role', 'is_active')}
        ),
    )

    ordering = ('-date_joined',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'gender', 'dob', 'address', 'slug')
    search_fields = ('user__full_name', 'phone', 'gender')
    list_filter = ('gender',)
    readonly_fields = ('slug',)