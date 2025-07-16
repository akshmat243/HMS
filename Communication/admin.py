from django.contrib import admin
from .models import Notification, Message, Feedback

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'sent_to', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('title', 'sent_to__full_name')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender', 'receiver', 'is_read', 'sent_at')
    list_filter = ('is_read',)
    search_fields = ('subject', 'sender__full_name', 'receiver__full_name')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'rating', 'submitted_at')
    search_fields = ('user__full_name',)
    list_filter = ('rating',)
