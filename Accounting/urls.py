from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, TransactionViewSet, DashboardStatsView,ExportExcelView, DownloadPDFView
from django.urls import path, include

router = DefaultRouter()
router.register(r'accounts', AccountViewSet)
router.register(r'transactions', TransactionViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/export-excel/', ExportExcelView.as_view(), name='export-excel'),
    path('api/download-pdf/', DownloadPDFView.as_view(), name='download-pdf'),
]
