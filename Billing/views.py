from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from django.utils import timezone
from MBP.views import ProtectedModelViewSet
from .models import Invoice, InvoiceItem, Payment
from .serializers import InvoiceSerializer, InvoiceItemSerializer, PaymentSerializer
import openpyxl
from openpyxl.styles import Font, Alignment
from django.http import HttpResponse
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


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
    
    @action(detail=False, methods=['get'], url_path='summary')
    def invoice_summary(self, request):
        user = request.user
        
        # Content type to EXCLUDE
        exclude_ct = ContentType.objects.get(app_label='inventory', model='purchaseorder')

        if not user.is_staff and not user.is_superuser:
            qs = Invoice.objects.filter(issued_to=user).exclude(content_type=exclude_ct)

        # USER IS ADMIN  only invoices created for his own hotel/business
        elif user.is_staff and not user.is_superuser:
            qs = Invoice.objects.filter(created_by=user).exclude(content_type=exclude_ct)

        # USER IS SUPERUSER all invoices from all admins (except Purchase Order)
        else:
            qs = Invoice.objects.exclude(content_type=exclude_ct)
       
        # TOTAL INVOICES (issued_to user)
        total_invoices = qs.count()

        # PENDING
        pending_invoices = qs.filter(status='unpaid').count()

        # OVERDUE
        overdue_invoices = qs.filter(
            status='unpaid',
            due_date__lt=timezone.now().date()
        ).count()

        # ⭐ TOTAL REVENUE = sum of paid invoice amounts EXCEPT inventory purchase order invoices
        total_revenue = qs.filter(
            status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        return Response({
            "total_revenue": float(total_revenue),
            "total_invoices": total_invoices,
            "pending_invoices": pending_invoices,
            "overdue_invoices": overdue_invoices
        })
    
    @action(detail=False, methods=['post'], url_path='export')
    def export_invoices(self, request):
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        if not start_date or not end_date:
            return Response({"error": "start_date and end_date are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Filter invoices
        invoices = Invoice.objects.filter(
            issued_at__date__gte=start_date,
            issued_at__date__lte=end_date
        ).order_by('-issued_at')

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Invoices"

        # Header row
        headers = [
            "Invoice No", "Customer Name", "Issued Date",
            "Due Date", "Total Amount", "Amount Paid","Balance Due", "Status"
        ]

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")

        # Insert invoice data
        for row, invoice in enumerate(invoices, start=2):
            balance_due = float(invoice.total_amount) - float(invoice.amount_paid)

            ws.cell(row=row, column=1, value=invoice.slug)
            ws.cell(row=row, column=2, value=invoice.customer_name)
            ws.cell(row=row, column=3, value=str(invoice.issued_at.date()))
            ws.cell(row=row, column=4, value=str(invoice.due_date))
            ws.cell(row=row, column=5, value=float(invoice.total_amount))
            ws.cell(row=row, column=6, value=float(invoice.amount_paid))
            ws.cell(row=row, column=7, value=balance_due)
            ws.cell(row=row, column=8, value=invoice.status)

        # Prepare response
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="invoices_{start_date}_to_{end_date}.xlsx"'

        wb.save(response)
        return response
    


    @action(detail=False, methods=['get'], url_path='recent-invoices')
    def recent_invoices(self, request):
        today = timezone.now().date()
        
        invoices = Invoice.objects.filter(
            issued_at__date=today
        ).order_by('-issued_at')

        serializer = self.get_serializer(invoices, many=True)
        return Response(serializer.data)



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
