from rest_framework import serializers
from .models import Notification, Message, Feedback, Subscriber , OutgoingMessage , MessageTemplate
from django.utils.text import slugify
import uuid

from django.core.validators import validate_email
import re
from .models import OutgoingMessage


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

class NewsletterSerializer(serializers.ModelSerializer):

    class Meta:
        model = Subscriber
        fields = ['email']

    def validate_email(self, value):
        if value.strip() == "":
            raise serializers.ValidationError("Email cannot be empty.")
        return value
    






PHONE_RE = re.compile(r'^\d{10}$')

class OutgoingMessageSerializer(serializers.ModelSerializer):
    save_template = serializers.BooleanField(write_only=True, required=False, default=False)
    schedule_at = serializers.DateTimeField(write_only=True, required=False, allow_null=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = OutgoingMessage
        fields = [
            'id','slug','channel','recipient','subject','message',
            'status','sent_at','created_by','created_at',
            'save_template','schedule_at'
        ]
        read_only_fields = ['id','status','sent_at','created_at','created_by']

    def validate(self, data):
        ch = data.get('channel')
        rec = str(data.get('recipient','')).strip()
        if ch == 'email':
            try:
                validate_email(rec)
            except Exception:
                raise serializers.ValidationError({"recipient":"Enter a valid email for email channel."})
        elif ch in ('whatsapp','sms'):
            if not PHONE_RE.match(rec):
                raise serializers.ValidationError({"recipient":"Phone number must be 10 digits for SMS/WhatsApp."})
        else:
            raise serializers.ValidationError({"channel":"Invalid channel."})
        return data





class MessageTemplateSerializer(serializers.ModelSerializer):
    use_count = serializers.SerializerMethodField()
    created_time = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = MessageTemplate
        fields = ['id','slug', 'name', 'channel', 'created_time', 'use_count']

    def get_use_count(self, obj):
        # best-effort count: count OutgoingMessage with same subject+body
        return obj.usage_history.count()
    

class UseTemplateSerializer(serializers.Serializer):
    recipient = serializers.CharField()
    subject = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    send = serializers.BooleanField(required=False, default=False)        # whether to actually send now
    schedule_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, data):
        # context must set 'channel'
        channel = self.context.get('channel')
        rec = data.get('recipient')
        if not rec:
            raise serializers.ValidationError({"recipient":"This field is required."})

        if channel == 'email':
            from django.core.validators import validate_email
            try:
                validate_email(rec)
            except Exception:
                raise serializers.ValidationError({"recipient":"Invalid email address."})
        else:
            # phone validation: accept digits and +; require at least 10 digits
            digits = ''.join([c for c in str(rec) if c.isdigit()])
            if len(digits) < 10:
                raise serializers.ValidationError({"recipient":"Invalid phone number."})

        # schedule_at (if provided) should be a future datetime — optional check
        sched = data.get('schedule_at')
        if sched:
            from django.utils import timezone
            if sched <= timezone.now():
                raise serializers.ValidationError({"schedule_at":"Must be a future datetime."})

        return data
