from django.contrib import admin
from .models import Page, FAQ, Banner, MetaTag

@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'created_at')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title', 'slug')
    list_filter = ('is_published',)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'is_active')
    search_fields = ('question', 'category')
    list_filter = ('is_active', 'category')


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'subtitle', 'link', 'is_active')
    search_fields = ('title', 'subtitle')
    list_filter = ('is_active',)


@admin.register(MetaTag)
class MetaTagAdmin(admin.ModelAdmin):
    list_display = ('page', 'meta_title')
    search_fields = ('meta_title', 'keywords')
