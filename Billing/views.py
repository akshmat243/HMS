from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum
from django.utils import timezone
from MBP.views import ProtectedModelViewSet
from .models import Invoice, InvoiceItem, Payment
from .serializers import InvoiceSerializer, InvoiceItemSerializer, PaymentSerializer

class InvoiceViewSet(ProtectedModelViewSet):
    queryset = Invoice.objects.all().select_related('booking', 'issued_to').prefetch_related('items', 'payments')
    serializer_class = InvoiceSerializer
    model_name = 'Invoice'
    lookup_field = 'slug'


class InvoiceItemViewSet(ProtectedModelViewSet):
    queryset = InvoiceItem.objects.all().select_related('invoice')
    serializer_class = InvoiceItemSerializer
    model_name = 'InvoiceItem'


class PaymentViewSet(ProtectedModelViewSet):
    queryset = Payment.objects.all().select_related('invoice')
    serializer_class = PaymentSerializer
    model_name = 'Payment'
    
    @action(detail=False, methods=['get'], url_path='today-revenue')
    def today_revenue(self, request):
        today = timezone.now().date()

        revenue = Payment.objects.filter(payment_date__date=today).aggregate(
            total_revenue=Sum('amount_paid')
        )['total_revenue'] or 0

        return Response({
            "date": today,
            "total_revenue": round(revenue, 2)
        })
