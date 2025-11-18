from rest_framework import serializers
from .models import Supplier, InventoryItem, InventoryCategory, PurchaseOrder, PurchaseOrderItem
from datetime import date
from Billing.models import Invoice, Payment
from django.contrib.contenttypes.models import ContentType


# Supplier
class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'

    def validate_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Supplier name must be at least 3 characters long.")
        return value

    def validate_email(self, value):
        if value and not value.endswith(".com"):
            raise serializers.ValidationError("Supplier email must be a valid domain (e.g. example@gmail.com).")
        return value

    def validate_rating(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 0 and 5.")
        return value


# Category
class InventoryCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryCategory
        fields = '__all__'

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Category name must have at least 2 letters.")
        return value


# Item
class InventoryItemSerializer(serializers.ModelSerializer):

    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=InventoryCategory.objects.all()
    )
    supplier = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Supplier.objects.all()
    )
    class Meta:
        model = InventoryItem
        fields = '__all__'
        read_only_fields = ['total_value', 'status', 'last_restocked']

    def validate(self, data):
        min_stock = data.get('min_stock', 0)
        max_stock = data.get('max_stock', 0)
        stock_level = data.get('stock_level', 0)

        if min_stock >= max_stock:
            raise serializers.ValidationError({
                "min_stock": "Minimum stock must be less than maximum stock."
            })

        if stock_level < 0:
            raise serializers.ValidationError({
                "stock_level": "Stock level cannot be negative."
            })

        if data.get('cost_per_unit', 0) < 0:
            raise serializers.ValidationError({
                "cost_per_unit": "Cost per unit cannot be negative."
            })

        if data.get('total_value', 0) < 0:
            raise serializers.ValidationError({
                "total_value": "Total value cannot be negative."
            })

        if data.get('last_restocked') and data['last_restocked'] > date.today():
            raise serializers.ValidationError({
                "last_restocked": "Restock date cannot be in the future."
            })

        return data


# purchase order
class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    total_cost = serializers.ReadOnlyField()
    # order = serializers.PrimaryKeyRelatedField(read_only=True)
    order = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=PurchaseOrder.objects.all()
    )

    item = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=InventoryItem.objects.all()
    )

    class Meta:
        model = PurchaseOrderItem
        fields = ['slug', 'order', 'item', 'quantity', 'cost_per_unit', 'total_cost']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

    def validate_cost_per_unit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Cost per unit must be greater than 0.")
        return value


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Supplier.objects.all()
    )

    items = PurchaseOrderItemSerializer(many=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = ['slug', 'supplier', 'status', 'created_at', 'items']
        read_only_fields = ['slug', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        admin_user = request.user if request else None

        # Get items from input
        items_data = validated_data.pop('items', []) if 'items' in validated_data else self.initial_data.get('items', [])

        # Prevent duplicate admin kwarg
        validated_data.pop('admin', None)

        # Create main Purchase Order
        order = PurchaseOrder.objects.create(admin=admin_user, **validated_data)

        # Add items & calculate total
        total_amount = 0
        for item_data in items_data:
            item_slug = item_data.get('item')
            try:
                item_obj = InventoryItem.objects.get(slug=item_slug)
            except InventoryItem.DoesNotExist:
                raise serializers.ValidationError({"item": f"Invalid item slug '{item_slug}'"})

            purchase_item = PurchaseOrderItem.objects.create(
                order=order,
                item=item_obj,
                quantity=item_data.get('quantity', 0),
                cost_per_unit=item_data.get('cost_per_unit', 0),
                admin=admin_user
            )
            total_amount += purchase_item.quantity * purchase_item.cost_per_unit

        # Save total amount to order
        order.total_amount = total_amount
        order.save()

        # ===== Auto Invoice Generation =====
        #from django.contrib.contenttypes.models import ContentType
        content_type = ContentType.objects.get_for_model(order)
        invoice = Invoice.objects.create(
            content_type=content_type,
            object_id=order.id,
            issued_to=admin_user,
            customer_name=order.admin.full_name,
            total_amount=total_amount,
            amount_paid=0,
            status='unpaid'
        )

        # ===== Auto Payment Record =====
        Payment.objects.create(
            invoice=invoice,
            amount_paid=0,
            method='cash'
        )

        return order
