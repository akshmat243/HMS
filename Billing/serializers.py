from rest_framework import serializers
from .models import Invoice, InvoiceItem, Payment


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'invoice', 'description', 'amount']
        extra_kwargs = {
            'invoice': {'required': False}
        }


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'invoice', 'amount_paid', 'payment_date', 'method', 'reference']
        read_only_fields = ['payment_date']
        extra_kwargs = {
            'invoice': {'required': False}
        }


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=False)
    payments = PaymentSerializer(many=True, required=False)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'slug', 'booking', 'issued_to', 'issued_at', 'due_date',
            'total_amount', 'status', 'notes', 'items', 'payments'
        ]
        read_only_fields = ['slug', 'issued_at', 'total_amount']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        payments_data = validated_data.pop('payments', [])
        invoice = Invoice.objects.create(**validated_data)

        total = 0
        for item_data in items_data:
            item = InvoiceItem.objects.create(invoice=invoice, **item_data)
            total += item.amount

        for payment_data in payments_data:
            Payment.objects.create(invoice=invoice, **payment_data)

        invoice.total_amount = total
        invoice.save()
        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        payments_data = validated_data.pop('payments', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            total = 0
            for item_data in items_data:
                item = InvoiceItem.objects.create(invoice=instance, **item_data)
                total += item.amount
            instance.total_amount = total
            instance.save()

        if payments_data is not None:
            instance.payments.all().delete()
            for payment_data in payments_data:
                Payment.objects.create(invoice=instance, **payment_data)

        return instance
