from rest_framework import serializers
from .models import Campaign, Promotion

class CampaignSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    class Meta:
        model = Campaign
        fields = '__all__'

    def validate_name(self, value):
        qs = Campaign.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Campaign with this name already exists.")
        return value


class PromotionSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    class Meta:
        model = Promotion
        fields = '__all__'

    def validate_title(self, value):
        qs = Promotion.objects.filter(title=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Promotion with this title already exists.")
        return value
