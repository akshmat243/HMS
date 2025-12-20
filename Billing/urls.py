from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (InvoiceViewSet,InvoiceItemViewSet,
                    PaymentViewSet,RevenueAnalyticsView,
                    TopAnalyticsView,DashboardStatsView,
                    CustomerAnalyticsView,
                    RecentActivityViewSet)

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'invoice-items', InvoiceItemViewSet, basename='invoiceitem')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'recent-activities', RecentActivityViewSet, basename='recent-activites')
# router.register(r'dashboard-activities', DashboardActivityViewSet, basename='dashboard-activities')


invoice_summary = InvoiceViewSet.as_view({'get': 'summary'})
invoice_export = InvoiceViewSet.as_view({'post': 'export'})

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/invoices/summary/', invoice_summary, name='invoice-summary'),
    path('api/invoices/export/', invoice_export, name='invoice-export'),
    path('api/analytics/', RevenueAnalyticsView.as_view(), name='revenue-analytics'),
    path('api/analytics/top-performing/', TopAnalyticsView.as_view(), name='top-performing'),
    path('api/analytics/reports/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/analytics/customers-insight/', CustomerAnalyticsView.as_view(), name='customer-analytics'),
]
