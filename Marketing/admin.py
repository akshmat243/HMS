from django.contrib import admin
from .models import Campaign, Promotion , CampaignEvent

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'budget', 'status')
    list_filter = ('status',)
    search_fields = ('name',)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title',)



@admin.register(CampaignEvent)
class CampaignEventAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'event_type', 'user_id', 'session_id', 'created_at')  
    list_filter = ('event_type',)
    search_fields = ('campaign__name',)