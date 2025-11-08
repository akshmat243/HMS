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
    balance_due = serializers.ReadOnlyField()

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
