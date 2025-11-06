from rest_framework import serializers
from .models import Page, FAQ, Banner, MetaTag


class MetaTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetaTag
        fields = '__all__'
        read_only_fields = ['id']


class PageSerializer(serializers.ModelSerializer):
    meta_tags = MetaTagSerializer(required=False)

    class Meta:
        model = Page
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']

    def validate_title(self, value):
        if self.instance:
            qs = Page.objects.filter(title=value).exclude(id=self.instance.id)
        else:
            qs = Page.objects.filter(title=value)
        if qs.exists():
            raise serializers.ValidationError("A page with this title already exists.")
        return value

    def create(self, validated_data):
        meta_data = validated_data.pop('meta_tags', None)
        page = super().create(validated_data)
        if meta_data:
            MetaTag.objects.update_or_create(page=page, defaults=meta_data)
        return page

    def update(self, instance, validated_data):
        meta_data = validated_data.pop('meta_tags', None)
        page = super().update(instance, validated_data)
        if meta_data:
            MetaTag.objects.update_or_create(page=page, defaults=meta_data)
        return page


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = '__all__'
        read_only_fields = ['id']

    def validate_question(self, value):
        qs = FAQ.objects.filter(question=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This FAQ already exists.")
        return value


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = '__all__'
        read_only_fields = ['id']

from rest_framework import serializers
from .models import SidebarApp

class SidebarAppSerializer(serializers.ModelSerializer):
    class Meta:
        model = SidebarApp
        fields = [
            'id', 'name', 'slug', 'label', 'icon', 'route', 'order', 'is_active', 'group', 'roles_allowed'
        ]
        read_only_fields = ['slug']

    def validate_name(self, value):
        qs = SidebarApp.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A sidebar app with this name already exists.")
        return value

    def validate_route(self, value):
        if not value.strip():
            raise serializers.ValidationError("Route field cannot be empty.")
        return value

    def validate_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Order must be a non-negative integer.")
        return value

    def validate_roles_allowed(self, value):
        # Optionally validate roles_allowed format (comma separated string)
        if value:
            roles = [role.strip() for role in value.split(',')]
            if any(not role for role in roles):
                raise serializers.ValidationError("Each role name must be non-empty.")
        return value
