from rest_framework import serializers
from .models import Notification, Message, Feedback
from django.utils.text import slugify
import uuid


class NotificationSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False)

    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at', 'is_read']

    def create(self, validated_data):
        if 'slug' not in validated_data:
            base = f"{validated_data.get('title', '')[:30]}-{uuid.uuid4().hex[:6]}"
            validated_data['slug'] = slugify(base)
        return super().create(validated_data)

    def validate_title(self, value):
        user = self.initial_data.get('sent_to')
        if Notification.objects.filter(title=value, sent_to=user).exists():
            raise serializers.ValidationError("Duplicate notification title for the same user.")
        return value


class MessageSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False)

    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['sent_at', 'is_read']

    def create(self, validated_data):
        if 'slug' not in validated_data:
            base = f"{validated_data.get('subject', '')[:30]}-{uuid.uuid4().hex[:6]}"
            validated_data['slug'] = slugify(base)
        return super().create(validated_data)

    def validate(self, data):
        if data['sender'] == data['receiver']:
            raise serializers.ValidationError("Sender and receiver cannot be the same.")
        return data


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = '__all__'
        read_only_fields = ['submitted_at']

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value
