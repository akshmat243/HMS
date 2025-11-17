from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from django.utils import timezone
from MBP.views import ProtectedModelViewSet
from .models import Invoice, InvoiceItem, Payment
from .serializers import InvoiceSerializer, InvoiceItemSerializer, PaymentSerializer

class InvoiceViewSet(ProtectedModelViewSet):
    # queryset = Invoice.objects.select_related('issued_to').prefetch_related('content_type')
    def get_queryset(self):
        user = self.request.user
        return Invoice.objects.filter(issued_to=user).select_related('issued_to', 'content_type')
    
    serializer_class = InvoiceSerializer
    model_name = 'Invoice'
    lookup_field = 'slug'

    @action(detail=True, methods=['patch'], url_path='pay')
    def pay_invoice(self, request, slug=None):
        invoice = self.get_object()
        amount = request.data.get('amount_paid', None)

        if amount is None:
            return Response({"error": "amount_paid is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
        except ValueError:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        #  Update amount paid
        invoice.amount_paid += amount
        invoice.save()

        serializer = self.get_serializer(invoice)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InvoiceItemViewSet(ProtectedModelViewSet):
    queryset = InvoiceItem.objects.all().select_related('invoice')
    serializer_class = InvoiceItemSerializer
    model_name = 'InvoiceItem'
    lookup_field = 'slug'


class PaymentViewSet(ProtectedModelViewSet):
    queryset = Payment.objects.all().select_related('invoice')
    serializer_class = PaymentSerializer
    model_name = 'Payment'
    lookup_field = 'slug'
    
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
