from rest_framework import serializers
from .models import Campaign, Promotion , CampaignEvent


class CampaignSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)
    hotel = serializers.SlugRelatedField(slug_field='name', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)

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
    hotel = serializers.SlugRelatedField(slug_field='name', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)


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

    def validate(self, data):
        start = data.get('start_date') or getattr(self.instance, 'start_date', None)
        end = data.get('end_date') or getattr(self.instance, 'end_date', None)

        if start and end and start > end:
            raise serializers.ValidationError({"end_date": "End date must be the same or after start date."})
        return data
    



class CampaignEventSerializer(serializers.ModelSerializer):
    # campaign returned as slug (read-only) — input MUST NOT provide campaign
    campaign = serializers.SlugRelatedField(read_only=True, slug_field='slug')
    # hotel returned as slug if exists; else fallback to PK string
    hotel = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CampaignEvent
        # do NOT require campaign/hotel in input -> they are set server-side
        fields = ('id', 'campaign', 'hotel', 'event_type', 'user_id', 'session_id', 'created_at')
        read_only_fields = ('id', 'campaign', 'hotel', 'created_at')

    def get_hotel(self, obj):
        hotel = getattr(obj, 'hotel', None)
        if not hotel:
            return None
        # prefer slug if hotel has one
        return getattr(hotel, 'slug', None) or getattr(hotel, 'name', None) or str(getattr(hotel, 'id', None))

    def validate(self, data):
        # require at least one of user_id or session_id
        if not data.get('user_id') and not data.get('session_id'):
            raise serializers.ValidationError("Either user_id or session_id must be provided.")
        # validate event_type choices (model has choices so this is optional but safer)
        if data.get('event_type') not in dict(self.Meta.model.EVENT_CHOICES):
            raise serializers.ValidationError({"event_type": "Invalid event_type."})
        return data