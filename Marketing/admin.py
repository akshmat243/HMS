from django.contrib import admin
from .models import Campaign, Promotion

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
