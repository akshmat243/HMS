from rest_framework import serializers
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from Billing.models import Invoice, InvoiceItem
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation, Restaurant, RestaurantMedia
)
from Hotel.models import Hotel
from Hotel.utils import ensure_module
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
            'pincode', 'contact_number', 'email', 'logo', 'cover_image', 'status', 'rating',
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
        
        ensure_module(owner, "restaurant")

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
    restaurant = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Restaurant.objects.all()
    )

    class Meta:
        model = MenuCategory
        fields = "__all__"
        read_only_fields = ["slug"]

    def validate_name(self, value):
        restaurant_slug = self.initial_data.get("restaurant")
        restaurant = Restaurant.objects.filter(slug=restaurant_slug).first()

        if not restaurant:
            raise serializers.ValidationError("Invalid restaurant.")

        qs = MenuCategory.objects.filter(
            name__iexact=value,
            restaurant=restaurant
        )

        if self.instance:
            qs = qs.exclude(id=self.instance.id)

        if qs.exists():
            raise serializers.ValidationError(
                "This category already exists for the restaurant."
            )

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
    restaurant = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Restaurant.objects.all()
    )

    last_status_time = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = "__all__"
        read_only_fields = ["slug", "table_code", "status_updated_at"]

    def get_last_status_time(self, obj):
        minutes = obj.get_last_status_time()
        if minutes is None:
            return None
        return f"{minutes} min"

    def validate_number(self, value):
        restaurant_slug = self.initial_data.get("restaurant")
        restaurant = Restaurant.objects.filter(slug=restaurant_slug).first()

        if not restaurant:
            raise serializers.ValidationError("Invalid restaurant.")

        qs = Table.objects.filter(
            number=value,
            restaurant=restaurant
        )

        if self.instance:
            qs = qs.exclude(id=self.instance.id)

        if qs.exists():
            raise serializers.ValidationError(
                "Table with this number already exists in this restaurant."
            )

        return value
    
    def validate(self, data):
        request = self.context.get("request")
        if not request:
            return data

        user = request.user
        restaurant = data.get("restaurant")

        # Admin → only own restaurant
        if user.role.name.lower() == "admin" and restaurant.owner != user:
            raise serializers.ValidationError(
                "You cannot manage tables for this restaurant."
            )

        # Staff → only assigned restaurant
        if user.role.name.lower() == "staff":
            if not hasattr(user, "staff_profile") or user.staff_profile.restaurant != restaurant:
                raise serializers.ValidationError(
                    "You cannot manage tables for this restaurant."
                )

        return data



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
    # 🔹 Incoming
    restaurant = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Restaurant.objects.all(),
        write_only=True
    )

    table = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Table.objects.all(),
        allow_null=True,
        required=False,
        write_only=True
    )

    # 🔹 Outgoing
    table_code = serializers.SerializerMethodField()
    restaurant_slug = serializers.CharField(
        source="restaurant.slug",
        read_only=True
    )

    order_items = OrderItemSerializer(many=True, required=False)
    status_duration = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantOrder
        fields = [
            "slug", "order_code",
            "restaurant", "restaurant_slug",
            "table", "table_code",

            "guest_name", "guest_phone", "remarks", "status",
            "order_time", "completed_at",

            "order_items",

            "total_quantity", "subtotal",
            "sgst", "cgst",
            "discount", "discount_rule",
            "grand_total",

            "status_duration",
        ]

        read_only_fields = [
            "slug", "order_code", "table_code",
            "order_time", "completed_at",
            "total_quantity", "subtotal",
            "sgst", "cgst",
            "discount", "discount_rule",
            "grand_total",
            "status_duration",
        ]

    # ------------------------
    # HELPERS
    # ------------------------

    def get_table_code(self, obj):
        return obj.table.table_code if obj.table else None

    def get_status_duration(self, obj):
        if not obj.status_updated_at:
            return "0 min"
        diff = timezone.now() - obj.status_updated_at
        return f"{int(diff.total_seconds() // 60)} min"

    # ------------------------
    # CREATE
    # ------------------------

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        items_data = validated_data.pop("order_items", [])
        restaurant = validated_data.get("restaurant")
        table = validated_data.get("table")

        # ✅ ROLE-BASED RESTAURANT OWNERSHIP CHECK
        if user.role.name.lower() == "admin":
            if restaurant.owner != user:
                raise serializers.ValidationError(
                    "You cannot create orders for this restaurant."
                )

        if user.role.name.lower() == "staff":
            if not hasattr(user, "staff_profile") or user.staff_profile.restaurant != restaurant:
                raise serializers.ValidationError(
                    "You cannot create orders for this restaurant."
                )

        # ✅ Ensure table belongs to restaurant
        if table and table.restaurant != restaurant:
            raise serializers.ValidationError(
                "Selected table does not belong to this restaurant."
            )

        order = RestaurantOrder.objects.create(**validated_data)

        # ✅ Lock table
        if table:
            table.status = "occupied"
            table.save(update_fields=["status"])

        for item in items_data:
            OrderItem.objects.create(order=order, **item)

        order.refresh_from_db()
        return order

    # ------------------------
    # UPDATE
    # ------------------------

    def update(self, instance, validated_data):
        request = self.context["request"]
        user = request.user

        items_data = validated_data.pop("order_items", None)

        old_status = instance.status
        new_status = validated_data.get("status", old_status)

        old_table = instance.table
        new_table = validated_data.get("table", old_table)

        # ✅ Prevent cross-restaurant tampering
        if user.role.name.lower() == "admin":
            if instance.restaurant.owner != user:
                raise serializers.ValidationError(
                    "You cannot modify orders from another restaurant."
                )

        if user.role.name.lower() == "staff":
            if not hasattr(user, "staff_profile") or user.staff_profile.restaurant != instance.restaurant:
                raise serializers.ValidationError(
                    "You cannot modify orders from another restaurant."
                )

        # ✅ Table change handling
        if old_table != new_table:
            if old_table:
                old_table.status = "available"
                old_table.save(update_fields=["status"])
            if new_table:
                new_table.status = "occupied"
                new_table.save(update_fields=["status"])

        # ✅ Status → table logic
        if old_status != new_status:
            if new_status in ["completed", "cancelled"]:
                if new_table:
                    new_table.status = "available"
                    new_table.save(update_fields=["status"])
            elif new_status in ["preparing", "served"]:
                if new_table:
                    new_table.status = "occupied"
                    new_table.save(update_fields=["status"])

        # ✅ Apply updates
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # ✅ Replace items
        if items_data is not None:
            instance.order_items.all().delete()
            for item in items_data:
                OrderItem.objects.create(order=instance, **item)

        # ✅ Invoice creation (served)
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

            if not created:
                invoice.total_amount = instance.grand_total
                invoice.save(update_fields=["total_amount"])
                invoice.items.all().delete()

            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"Restaurant Order - {instance.order_code}",
                quantity=1,
                unit_price=instance.grand_total,
            )

        return instance


class TableReservationSerializer(serializers.ModelSerializer):
    table = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Table.objects.all()
    )

    class Meta:
        model = TableReservation
        fields = "__all__"
        read_only_fields = ["slug", "created_at", "status"]

    def validate(self, data):
        request = self.context.get("request")
        user = request.user

        table = data.get("table")
        reservation_date = data.get("reservation_date")
        reservation_time = data.get("reservation_time")

        restaurant = table.restaurant

        # ----------------------------------
        # ROLE-BASED RESTAURANT CHECK
        # ----------------------------------

        # Superuser → allowed
        if user.is_superuser:
            pass

        # Admin → only own restaurant
        elif user.role.name.lower() == "admin":
            if restaurant.owner != user:
                raise serializers.ValidationError(
                    "You cannot reserve tables for this restaurant."
                )

        # Staff → only assigned restaurant
        elif user.role.name.lower() == "staff":
            if not hasattr(user, "staff_profile") or user.staff_profile.restaurant != restaurant:
                raise serializers.ValidationError(
                    "You cannot reserve tables for this restaurant."
                )

        # Customer → restaurant must be open
        elif user.role.name.lower() == "customer":
            if restaurant.status != "open":
                raise serializers.ValidationError(
                    "This restaurant is not open for reservations."
                )

        else:
            raise serializers.ValidationError("You are not allowed to reserve tables.")

        # ----------------------------------
        # CHECK OVERLAPPING RESERVATION
        # ----------------------------------
        exists = TableReservation.objects.filter(
            table=table,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            status__in=["pending", "confirmed"],
        ).exists()

        if exists:
            raise serializers.ValidationError(
                "This table is already reserved at this time."
            )

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
    # Restaurant details
    restaurant_name = serializers.CharField(
        source="restaurant.name",
        read_only=True
    )
    restaurant_city = serializers.CharField(
        source="restaurant.city",
        read_only=True
    )
    restaurant_address = serializers.CharField(
        source="restaurant.address",
        read_only=True
    )
    restaurant_image = serializers.ImageField(
        source="restaurant.cover_image",
        read_only=True
    )
    restaurant_slug = serializers.CharField(
        source="restaurant.slug",
        read_only=True
    )

    class Meta:
        model = Table
        fields = [
            "id",
            "number",
            "capacity",
            "status",

            # restaurant info
            "restaurant_name",
            "restaurant_slug",
            "restaurant_city",
            "restaurant_address",
            "restaurant_image",
        ]

class RestaurantMediaSerializer(serializers.ModelSerializer):
    restaurant = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Restaurant.objects.all()
    )

    restaurant_name = serializers.CharField(
        source='restaurant.name',
        read_only=True
    )

    file = serializers.FileField(required=False)
    
    files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = RestaurantMedia
        fields = [
            'id',
            'restaurant',
            'restaurant_name',
            'slug',
            'file',
            'files',
            'media_type',
            'caption',
            'created_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at']

    def create(self, validated_data):
        files = validated_data.pop('files', None)

        # SINGLE FILE
        if not files:
            return super().create(validated_data)

        # MULTIPLE FILES
        media_objects = []
        for file in files:
            media = RestaurantMedia.objects.create(
                file=file,
                **validated_data
            )
            media_objects.append(media)

        return media_objects