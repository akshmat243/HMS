from rest_framework import serializers
from .models import Account, Transaction
from django.db import models


class AccountSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    class Meta:
        model = Account
        fields = '__all__'

    def validate_name(self, value):
        qs = Account.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("An account with this name already exists.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    account = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Account.objects.filter(is_active=True)
    )

    class Meta:
        model = Transaction
        fields = '__all__'

    def validate(self, data):
        account = data.get('account')
        amount = data.get('amount')
        tx_type = data.get('type')

        if amount <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")

        if tx_type == 'debit':
            # Calculate current balance
            total_credits = account.transactions.filter(type='credit').aggregate(total=models.Sum('amount'))['total'] or 0
            total_debits = account.transactions.filter(type='debit').aggregate(total=models.Sum('amount'))['total'] or 0
            current_balance = account.opening_balance + total_credits - total_debits

            if amount > current_balance:
                raise serializers.ValidationError(f"Insufficient funds. Current balance is ₹{current_balance}.")

        return data


class DashboardStatsSerializer(serializers.Serializer):
    """
    Serializer to define the structure of the dashboard JSON response.
    Mainly for documentation and validation purposes.
    """
    room_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    restaurant_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    staff_costs = serializers.DecimalField(max_digits=12, decimal_places=2)
    operating_expenses = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_profit = serializers.DecimalField(max_digits=12, decimal_places=2)


class MonthlyReportSerializer(serializers.Serializer):
    """
    Serializer for the list of monthly history at the bottom of the dashboard.
    """
    month = serializers.CharField()
    year = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    expenses = serializers.DecimalField(max_digits=12, decimal_places=2)
    profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()