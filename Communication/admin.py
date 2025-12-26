from django.contrib import admin
from .models import Notification, Message, Feedback, Subscriber,OutgoingMessage,MessageTemplate
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

@admin.register(Subscriber)
class SubscribeAdmin(admin.ModelAdmin):
    list_display = ('email', 'subscribed_at')
    # search_fields = ('email')
    # ordering = ('updated_at')

@admin.register(OutgoingMessage)
class OutgoingMessageAdmin(admin.ModelAdmin):
    # Shows channel (email/whatsapp), who it went to, status, and when
    list_display = ('id', 'channel', 'recipient', 'subject', 'status', 'created_at', 'sent_at')
    
    # Filter by channel (e.g., show only WhatsApp) or Status (e.g., show only Failed)
    list_filter = ('channel', 'status', 'created_at')
    
    # Search by recipient (email/phone) or subject
    search_fields = ('recipient', 'subject', 'message')
    
    # Make created_at read-only so it can't be tampered with easily
    readonly_fields = ('created_at', 'sent_at')


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    # Shows template name, channel, and use count
    list_display = ('name', 'channel', 'created_by', 'created_at', 'updated_at', 'get_use_count')
    
    list_filter = ('channel', 'created_at')
    search_fields = ('name', 'subject', 'body')
    
    # Function to show use_count in the admin list
    def get_use_count(self, obj):
        # This matches the new logic we added to models/serializers
        return obj.usage_history.count()
    get_use_count.short_description = 'Times Used'