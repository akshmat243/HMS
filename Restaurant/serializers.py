from rest_framework import serializers
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from Billing.models import Invoice, InvoiceItem
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation, Restaurant
)
from Hotel.models import Hotel
from django.core.validators import RegexValidator

from django.contrib.auth import get_user_model
User = get_user_model()

class RestaurantSerializer(serializers.ModelSerializer):
    owner_slug = serializers.SlugField(write_only=True, required=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = Restaurant
        fields = [
            'id', 'slug', 'name', 'description', 'address', 'city', 'state', 'country',
            'pincode', 'contact_number', 'email', 'logo', 'cover_image', 'status',
            'owner_slug', 'owner_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def create(self, validated_data):
        owner_slug = validated_data.pop('owner_slug')
        try:
            owner = User.objects.get(slug=owner_slug)
        except User.DoesNotExist:
            raise serializers.ValidationError({'owner_slug': 'Invalid admin user slug'})

        if str(owner.role).lower() != 'admin':
            raise serializers.ValidationError({'owner_slug': 'User must have Admin role'})

        if Restaurant.objects.filter(owner=owner).exists():
            raise serializers.ValidationError({'owner_slug': 'This admin already owns a Restaurant'})

        restaurant = Restaurant.objects.create(owner=owner, **validated_data)
        return restaurant

    def update(self, instance, validated_data):
        # Prevent changing owner except by superuser
        if 'owner_slug' in validated_data:
            request = self.context['request']
            if not request.user.is_superuser:
                raise serializers.ValidationError({'owner_slug': 'You cannot change restaurant admin.'})
            owner_slug = validated_data.pop('owner_slug')
            instance.owner = User.objects.get(slug=owner_slug)

        return super().update(instance, validated_data)


class MenuCategorySerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )

    class Meta:
        model = MenuCategory
        fields = '__all__'
        read_only_fields = ['slug']

    def validate_name(self, value):
        hotel_slug = self.initial_data.get('hotel')
        hotel = Hotel.objects.filter(slug=hotel_slug).first()
        if not hotel:
            raise serializers.ValidationError("Invalid hotel.")
        qs = MenuCategory.objects.filter(name=value, hotel=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This category already exists for the hotel.")
        return value


class MenuItemSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=MenuCategory.objects.all()
    )

    class Meta:
        model = MenuItem
        fields = '__all__'
        read_only_fields = ['slug']

    def validate(self, data):
        name = data.get('name', self.instance.name if self.instance else None)
        category = data.get('category', self.instance.category if self.instance else None)
        qs = MenuItem.objects.filter(name=name, category=category)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This item already exists in this category.")
        return data


class TableSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )
    
    last_status_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Table
        fields = '__all__'
        read_only_fields = ['slug']
    
    def get_last_status_time(self, obj):
        minutes = obj.get_last_status_time()
        if minutes is None:
            return None
        return f"{minutes} min"   


    def validate_number(self, value):
        hotel_slug = self.initial_data.get('hotel')
        hotel = Hotel.objects.filter(slug=hotel_slug).first()
        if not hotel:
            raise serializers.ValidationError("Invalid hotel.")
        qs = Table.objects.filter(number=value, hotel=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Table with this number already exists in this hotel.")
        return value

class OrderItemSerializer(serializers.ModelSerializer):
    menu_item = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=MenuItem.objects.all()
    )

    class Meta:
        model = OrderItem
        fields = ['slug', 'menu_item', 'quantity', 'price']
        read_only_fields = ['slug']

    def validate(self, data):
        """Ensure quantity and price are valid."""
        if data.get('quantity', 0) <= 0:
            raise serializers.ValidationError({"quantity": "Quantity must be greater than zero."})
        if data.get('price', 0) <= 0:
            raise serializers.ValidationError({"price": "Price must be greater than zero."})
        return data
    
class RestaurantOrderSerializer(serializers.ModelSerializer):
    table = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Table.objects.all(),
        allow_null=True,
        write_only=True
    )

    table_code = serializers.SerializerMethodField()
    hotel = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    order_items = OrderItemSerializer(many=True, required=False)
    status_duration = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantOrder
        fields = [
            'slug', 'order_code', 'table_code', 'hotel', 'table',
            'guest_name', 'guest_phone', 'remarks', 'status',
            'order_time', 'completed_at', 'order_items',
            'total_quantity', 'subtotal', 'sgst', 'cgst',
            'discount', 'discount_rule', 'grand_total',
            'status_duration'
        ]
        read_only_fields = [
            'slug', 'order_code', 'table_code', 'order_time',
            'completed_at', 'total_quantity', 'subtotal',
            'sgst', 'cgst', 'discount', 'discount_rule',
            'grand_total', 'status_duration'
        ]

    def get_table_code(self, obj):
        return obj.table.table_code if obj.table else None

    def get_status_duration(self, obj):
        if not obj.status_updated_at:
            return "0 min"
        diff = timezone.now() - obj.status_updated_at
        return f"{int(diff.total_seconds() // 60)} min"

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        # Assign hotel from logged-in user
        if hasattr(user, 'hotel_profile'):
            validated_data['hotel'] = user.hotel_profile.hotel
        elif hasattr(user, 'hotel'):
            validated_data['hotel'] = user.hotel
        else:
            raise serializers.ValidationError("User has no hotel assigned.")

        items_data = validated_data.pop('order_items', [])
        table = validated_data.get("table")
        
        # ✅ Ensure table belongs to same hotel
        if table and table.hotel != validated_data["hotel"]:
            raise serializers.ValidationError("This table does not belong to your hotel.")
        
        order = RestaurantOrder.objects.create(**validated_data)
        
        if table:
            table.status = "occupied"
            table.save(update_fields=["status"])

        for item in items_data:
            OrderItem.objects.create(order=order, **item)

        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('order_items', None)
        old_status = instance.status
        new_status = validated_data.get("status", old_status)
        old_table = instance.table
        new_table = validated_data.get("table", old_table)

        # ✅ Prevent cross-hotel tampering
        request = self.context.get("request")
        user = request.user
        user_hotel = getattr(user, "hotel_profile", None)
        if user_hotel:
            user_hotel = user_hotel.hotel
        else:
            user_hotel = getattr(user, "hotel", None)

        if instance.hotel != user_hotel:
            raise serializers.ValidationError("You cannot modify orders from another hotel.")

        # ✅ If table changed, update statuses
        if old_table != new_table:
            if old_table:
                old_table.status = "available"
                old_table.save(update_fields=["status"])
            if new_table:
                new_table.status = "occupied"
                new_table.save(update_fields=["status"])

        # ✅ If status changed → update table status
        if old_status != new_status:
            if new_status in ["completed", "cancelled"]:
                if new_table:
                    new_table.status = "available"
                    new_table.save(update_fields=["status"])

            elif new_status in ["preparing", "served"]:
                if new_table:
                    new_table.status = "occupied"
                    new_table.save(update_fields=["status"])

        # ✅ Apply validated data
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        # ✅ Replace order items
        if items_data is not None:
            instance.order_items.all().delete()
            for item in items_data:
                OrderItem.objects.create(order=instance, **item)
                
        if new_status == "served":
            from django.contrib.contenttypes.models import ContentType
            content_type = ContentType.objects.get_for_model(RestaurantOrder)

            invoice, created = Invoice.objects.get_or_create(
                content_type=content_type,
                object_id=instance.id,
                defaults={
                    "issued_to": user,
                    "total_amount": instance.grand_total,
                    "status": "unpaid",
                    "customer_name": instance.guest_name,
                },
            )

            # ✅ If invoice already exists → update it
            if not created:
                invoice.total_amount = instance.grand_total
                invoice.save(update_fields=["total_amount"])
                invoice.items.all().delete()

            # ✅ Add invoice item
            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"Restaurant Order - {instance.order_code}",
                quantity=1,
                unit_price=instance.grand_total,
            )

        return instance


class TableReservationSerializer(serializers.ModelSerializer):
    table = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Table.objects.all()
    )

    class Meta:
        model = TableReservation
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'status']

    def validate(self, data):
        table = data.get("table")
        date = data.get("reservation_date")
        time = data.get("reservation_time")

        # ✅ Check table belongs to user's hotel
        request = self.context.get("request")
        user = request.user
        hotel = getattr(user, "hotel_profile", None)
        if hotel:
            hotel = hotel.hotel
        else:
            hotel = getattr(user, "hotel", None)

        if table.hotel != hotel:
            raise serializers.ValidationError("This table does not belong to your hotel.")

        # ✅ Check for overlapping reservations
        existing = TableReservation.objects.filter(
            table=table,
            reservation_date=date,
            reservation_time=time,
            status__in=['pending', 'confirmed']
        )

        if existing.exists():
            raise serializers.ValidationError("This table is already reserved at this time.")

        return data

    def create(self, validated_data):
        table = validated_data["table"]
        reservation = TableReservation.objects.create(**validated_data)

        # ✅ Mark table as reserved
        table.status = "reserved"
        table.save(update_fields=["status"])

        return reservation


    
class RestaurantDashboardSerializer(serializers.Serializer):
    available_tables = serializers.IntegerField()
    active_orders = serializers.IntegerField()
    todays_revenue = serializers.FloatField()
    avg_wait_time = serializers.CharField()


from .models import BookingCallback
class BookingCallbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingCallback
        fields = '__all__'

    def validate_restaurant_name(self, value):
        """
        Check if the restaurant name exists in our Restaurant model.
        """
        # 1. Extra spaces hata dete hain (strip)
        restaurant_name = value.strip()

        # 2. Check karte hain database me
        # __iexact ka matlab hai case-insensitive (User 'Taj' likhe ya 'taj', dono chalega)
        if not Restaurant.objects.filter(name__iexact=restaurant_name).exists():
            raise serializers.ValidationError("Restaurant does not exist.")
        
        return restaurant_name


class TableSearchSerializer(serializers.ModelSerializer):
    # Hotel ki details fetch karne ke liye
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    hotel_city = serializers.CharField(source='hotel.city', read_only=True)
    hotel_address = serializers.CharField(source='hotel.address', read_only=True)
    hotel_image = serializers.ImageField(source='hotel.cover_image', read_only=True) # Agar Hotel model me image h to

    class Meta:
        model = Table
        fields = ['id', 'number', 'capacity', 'status', 'hotel_name', 'hotel_city', 'hotel_address', 'hotel_image']