from rest_framework import serializers
from .models import Lead, Customer, Interaction
from django.contrib.auth import get_user_model

User = get_user_model()


class LeadSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)
    assigned_to = serializers.SlugRelatedField(
        slug_field='full_name',
        queryset=User.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Lead
        fields = '__all__'

    def validate_email(self, value):
        qs = Lead.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A lead with this email already exists.")
        return value


class CustomerSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'

    def validate_email(self, value):
        qs = Customer.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A customer with this email already exists.")
        return value


class InteractionSerializer(serializers.ModelSerializer):
    customer = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Customer.objects.all()
    )
    handled_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Interaction
        fields = '__all__'
