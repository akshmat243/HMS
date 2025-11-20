from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SupplierView, InventoryItemView, InventoryCategoryView, PurchaseOrderView, inventory_dashboard_summary #'''PurchaseOrderItemView,'''

router = DefaultRouter()
router.register(r'suppliers', SupplierView, basename='inventory-suppliers')
router.register(r'categories', InventoryCategoryView, basename='inventory-categories')
router.register(r'items', InventoryItemView, basename='inventory-items')
router.register(r'purchase-orders', PurchaseOrderView, basename='inventory-purchase-order')
# router.register(r'purchase-order-items', PurchaseOrderItemView, basename='inventory-purchase-order-items')


urlpatterns = [
    path('api/', include(router.urls)),
    path('api/dashboard-summary/', inventory_dashboard_summary, name='inventory-dashboard-summary'),
]
