from rest_framework import serializers
from .models import Invoice, InvoiceItem, Payment
from MBP.models import AuditLog
from django.utils import timezone
from datetime import datetime
from django.utils.timesince import timesince
from Hotel.models import Room
import uuid

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
        # total = 0
        for item_data in items_data:
            item_data['invoice'] = invoice
            item = InvoiceItem.objects.create(**item_data)
            total += item.amount
        # invoice.total_amount = total
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


class RecentActivitySerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()
    status_color = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'title', 'value', 'status_color', 'time_ago', 'timestamp']

    def get_time_ago(self, obj):
        return timesince(obj.timestamp, timezone.now()) + " ago"

    def get_status_color(self, obj):
        if obj.model_name == 'HotelReview':
            return 'yellow'
        if obj.model_name == 'Booking':
            data = obj.new_data or {}
            if obj.action == 'create':
                return 'blue'
            if data.get('status') in ['checked_in', 'checked_out']:
                return 'purple'
            if data.get('payment_status') == 'paid':
                return 'green'
        return 'gray'

    def get_value(self, obj):
        data = obj.new_data or {}
        if obj.model_name == 'HotelReview':
            rating = data.get('rating', 5)
            return "⭐" * int(rating)
        if obj.model_name == 'Booking':
            amount = data.get('total_amount')
            if amount:
                return f"${amount}"
        return None

    def get_title(self, obj):
        data = obj.new_data or {}
        model = obj.model_name
        action = obj.action
        
        # --- REVIEWS ---
        if model == 'HotelReview':
            return "5-star review for restaurant service" if data.get('rating') == 5 else "New review received"

        # --- BOOKINGS ---
        if model == 'Booking':
            # Default fallback
            display_name = "Room" 
            raw_room_data = data.get('room') # ID (UUID) or Name (String)

            room_obj = None

            # STEP 1: Try finding Room Object
            if raw_room_data:
                # Case A: Check if UUID
                try:
                    uuid_obj = uuid.UUID(str(raw_room_data))
                    room_obj = Room.objects.filter(id=uuid_obj).first()
                except ValueError:
                    # Case B: It is a String (e.g., "300 - My Hotel")
                    # Hum koshish karenge room number se room dhoondne ki
                    str_data = str(raw_room_data)
                    if ' - ' in str_data:
                        # Split "300 - Hotel" -> Number: "300", Hotel: "Hotel"
                        parts = str_data.split(' - ')
                        r_num = parts[0]
                        h_name = parts[1]
                        # Try to find specific room
                        room_obj = Room.objects.filter(room_number=r_num, hotel__name=h_name).first()
                    else:
                        # Agar sirf "300" likha hai
                        room_obj = Room.objects.filter(room_number=str_data).first()

            # STEP 2: Extract Category Name if object found
            if room_obj and room_obj.room_category:
                display_name = room_obj.room_category.name  # ✅ Show "Deluxe", "Suite" etc.
            elif room_obj:
                display_name = f"Room {room_obj.room_number}" # Fallback to number if no category
            elif raw_room_data and ' - ' in str(raw_room_data):
                 # Fallback agar DB me room delete ho gaya ho par log me naam hai
                 display_name = str(raw_room_data).split(' - ')[0]

            # --- GENERATE TITLE ---
            
            # 1. Booking Creation
            if action == 'create':
                nights = 1
                check_in_str = data.get('check_in')
                check_out_str = data.get('check_out')

                if check_in_str and check_out_str:
                    try:
                        d1 = datetime.strptime(str(check_in_str), "%Y-%m-%d").date()
                        d2 = datetime.strptime(str(check_out_str), "%Y-%m-%d").date()
                        delta = d2 - d1
                        nights = delta.days if delta.days > 0 else 1
                    except ValueError:
                        pass 

                return f"{display_name} booked for {nights} nights"
            
            # 2. Status Updates
            status = data.get('status')
            if status == 'checked_in':
                return f"Guest checked in to {display_name}"
            if status == 'checked_out':
                return f"Guest checked out from {display_name}"
            
            # 3. Payments
            if data.get('payment_status') == 'paid':
                return f"Payment received for {display_name}"

        return f"Activity on {model}"