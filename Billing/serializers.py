from rest_framework import serializers
from .models import Invoice, InvoiceItem, Payment


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = '__all__'
        read_only_fields = ('id', 'slug', 'amount')

    def validate(self, data):
        if data['quantity'] <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        if data['unit_price'] <= 0:
            raise serializers.ValidationError("Unit price must be greater than 0.")
        return data


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('id', 'slug', 'payment_date')

    def validate(self, data):
        invoice = data.get('invoice')
        amount = data.get('amount_paid')
        total_paid = invoice.payments.aggregate(total=serializers.Sum('amount_paid'))['total'] or 0

        if total_paid + amount > invoice.total_amount:
            raise serializers.ValidationError("Payment exceeds total invoice amount.")
        return data


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=False)
    payments = PaymentSerializer(many=True, required=False)
    balance_due = serializers.SerializerMethodField()
    #issued_to_name = serializers.SerializerMethodField()
    issued_to = serializers.CharField(source="issued_to.full_name", read_only=True)


    def get_balance_due(self, obj):
        return max(obj.total_amount - obj.amount_paid, 0)
    
    # def get_issued_to_name(self, obj):
    #     related = obj.related_object

    #     # CASE 1 → Booking Invoice → Guest name
    #     if related:
    #     # If related object has guests (Booking model)
    #         if hasattr(related, "guests"):
    #             guest = related.guests.first()
    #             if guest:
    #                 return f"{guest.first_name} {guest.last_name or ''}".strip()

    #     # If Booking model has user (fallback)
    #         if hasattr(related, "user"):
    #             return related.user.full_name or related.user.email

    #     # CASE 2 → Default: issued_to user name
    #     if obj.issued_to:
    #         return obj.issued_to.full_name or obj.issued_to.email

    #     return None


    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ('id', 'slug', 'issued_at', 'status')

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        invoice = Invoice.objects.create(**validated_data)
        total = 0
        for item_data in items_data:
            item_data['invoice'] = invoice
            item = InvoiceItem.objects.create(**item_data)
            total += item.amount
        invoice.total_amount = total
        invoice.save()
        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            total = 0
            for item_data in items_data:
                item_data['invoice'] = instance
                item = InvoiceItem.objects.create(**item_data)
                total += item.amount
            instance.total_amount = total
            instance.save()

        return instance


    def validate(self, data):
        total = data.get('total_amount', getattr(self.instance, 'total_amount', None))
        paid = data.get('amount_paid', getattr(self.instance, 'amount_paid', 0))

        if paid and total and paid > total:
            raise serializers.ValidationError({
                "amount_paid": "Amount paid cannot be greater than total amount."})
        return data
