# inventory/views.py

from MBP.views import ProtectedModelViewSet   # ✅ using your prebuilt secure base class
from .models import Supplier, InventoryItem, InventoryCategory, PurchaseOrder, PurchaseOrderItem
from .serializers import (
    SupplierSerializer, InventoryItemSerializer, InventoryCategorySerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer
)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Q


class SupplierView(ProtectedModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    model_name = 'Supplier'
    lookup_field = 'slug'

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

    # agar role admin hai, sirf uska hi data dikhao
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(admin=user)

    # agar superuser hai to sab dikhao
        if user.is_superuser:
            return qs

    # kisi aur role ke liye kuch nahi
        return qs.none()


class InventoryCategoryView(ProtectedModelViewSet):
    queryset = InventoryCategory.objects.all()
    serializer_class = InventoryCategorySerializer
    model_name = 'InventoryCategory'
    lookup_field = 'slug'

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

    # agar role admin hai, sirf uska hi data dikhao
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(admin=user)

    # agar superuser hai to sab dikhao
        if user.is_superuser:
            return qs

    # kisi aur role ke liye kuch nahi
        return qs.none()

class InventoryItemView(ProtectedModelViewSet):
    queryset = InventoryItem.objects.all().select_related('supplier', 'category')
    serializer_class = InventoryItemSerializer
    model_name = 'InventoryItem'
    lookup_field = 'slug'   

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

    # agar role admin hai, sirf uska hi data dikhao
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(admin=user)

    # agar superuser hai to sab dikhao
        if user.is_superuser:
            return qs

    # kisi aur role ke liye kuch nahi
        return qs.none()

class PurchaseOrderView(ProtectedModelViewSet):
    queryset = PurchaseOrder.objects.all().prefetch_related('items')
    serializer_class = PurchaseOrderSerializer
    model_name = 'PurchaseOrder'
    lookup_field = 'slug'

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

    # agar role admin hai, sirf uska hi data dikhao
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(admin=user)

    # agar superuser hai to sab dikhao
        if user.is_superuser:
            return qs

    # kisi aur role ke liye kuch nahi
        return qs.none()

class PurchaseOrderItemView(ProtectedModelViewSet):
    queryset = PurchaseOrderItem.objects.all()
    serializer_class = PurchaseOrderItemSerializer
    model_name = 'PurchaseOrderItem'
    lookup_field = 'slug'

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

    # agar role admin hai, sirf uska hi data dikhao
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(admin=user)

    # agar superuser hai to sab dikhao
        if user.is_superuser:
            return qs

    # kisi aur role ke liye kuch nahi
        return qs.none()
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_dashboard_summary(request):
    user = request.user

    # Filter data based on admin user
    item_qs = InventoryItem.objects.all()
    supplier_qs = Supplier.objects.all()

    if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
        item_qs = item_qs.filter(admin=user)
        supplier_qs = supplier_qs.filter(admin=user)

    # 1️⃣ Total Items
    total_items = item_qs.count()

    # 2️⃣ Low Stock (Low + Critical)
    low_stock = item_qs.filter(Q(status='low') | Q(status='critical')).count()

    # 3️⃣ Total Value (sum of all items’ total_value)
    total_value = item_qs.aggregate(total=Sum('total_value'))['total'] or 0

    # 4️⃣ Total Suppliers
    total_suppliers = supplier_qs.count()

    data = {
        "total_items": total_items,
        "low_stock": low_stock,
        "total_value": round(total_value, 2),
        "total_suppliers": total_suppliers
    }

    return Response(data)
