from django.contrib import admin
from .models import Page, FAQ, Banner, MetaTag


class MetaTagInline(admin.StackedInline):
    model = MetaTag
    extra = 0
    max_num = 1


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'publish_date', 'created_at')
    list_filter = ('is_published', 'publish_date')
    search_fields = ('title', 'slug', 'content')
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [MetaTagInline]
    ordering = ('-created_at',)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'is_active', 'position')
    list_filter = ('is_active', 'category')
    search_fields = ('question', 'answer')
    ordering = ('position', 'question')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'start_date', 'end_date')
    list_filter = ('is_active',)
    search_fields = ('title', 'subtitle')
    readonly_fields = ('created_at', 'updated_at')
