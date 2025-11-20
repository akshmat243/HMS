from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InvoiceViewSet, InvoiceItemViewSet, PaymentViewSet

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'invoice-items', InvoiceItemViewSet, basename='invoiceitem')
router.register(r'payments', PaymentViewSet, basename='payment')


invoice_summary = InvoiceViewSet.as_view({'get': 'summary'})
invoice_export = InvoiceViewSet.as_view({'post': 'export'})

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/invoices/summary/', invoice_summary, name='invoice-summary'),
    path('api/invoices/export/', invoice_export, name='invoice-export'),
]
