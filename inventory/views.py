# inventory/views.py

from MBP.views import ProtectedModelViewSet   # ✅ using prebuilt secure base class
from .models import Supplier, InventoryItem, InventoryCategory, PurchaseOrder, PurchaseOrderItem
from .serializers import (
    SupplierSerializer, InventoryItemSerializer, InventoryCategorySerializer,
    PurchaseOrderSerializer)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Q, Count
from rest_framework import status

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
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(admin=user)
        if user.is_superuser:
            return qs
        return qs.none()

# class PurchaseOrderItemView(ProtectedModelViewSet):
#     queryset = PurchaseOrderItem.objects.all()
#     serializer_class = PurchaseOrderItemSerializer
#     model_name = 'PurchaseOrderItem'
#     lookup_field = 'slug'

#     def perform_create(self, serializer):
#         serializer.save(admin=self.request.user)

#     def get_queryset(self):
#         user = self.request.user
#         qs = super().get_queryset()

#     # agar role admin hai, sirf uska hi data dikhao
#         if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
#             return qs.filter(admin=user)

#     # agar superuser hai to sab dikhao
#         if user.is_superuser:
#             return qs

#     # kisi aur role ke liye kuch nahi
#         return qs.none()
    


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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_reports_overview(request):
    """
    Combined endpoint matching screenshot:
    - category_breakdown: list of {category, item_count, total_value}
    - stock_status: list of {status, item_count, percentage}
    """
    user = request.user
    qs = InventoryItem.objects.select_related('category')

    if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
        qs = qs.filter(admin=user)

    total_items = qs.count() or 1  # avoid division by zero

    # Category breakdown
    categories_raw = qs.values("category__name").annotate(
        item_count=Count("id"),
        total_value=Sum("total_value")
    )

    category_breakdown = []
    # Keep ordering consistent (optional: order by total_value desc)
    for c in categories_raw:
        category_breakdown.append({
            "category": c.get("category__name") or "Uncategorized",
            "item_count": c.get("item_count", 0),
            "total_value": round((c.get("total_value") or 0), 2)
        })

    # Stock status breakdown
    status_raw = qs.values("status").annotate(count=Count("id"))

    stock_status = []
    # ensure consistent order as in screenshot: Good, Low, Critical, Overstock
    order_map = {"good": 0, "low": 1, "critical": 2, "overstock": 3}
    # convert to list of dicts first
    for s in status_raw:
        status_key = s.get("status") or "good"
        cnt = s.get("count", 0)
        percentage = round((cnt / total_items) * 100, 1)
        stock_status.append({
            "status": status_key.capitalize(),
            "item_count": cnt,
            "percentage": percentage
        })

    # sort stock_status according to order_map if keys present
    stock_status.sort(key=lambda x: order_map.get(x['status'].lower(), 99))

    return Response({
        "category_breakdown": category_breakdown,
        "stock_status": stock_status
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def low_items_list(request):
    user = request.user
    qs = InventoryItem.objects.select_related('supplier', 'category').filter(Q(status='low') | Q(status='critical'))
    if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
        qs = qs.filter(admin=user)

    items = []
    for it in qs:
        items.append({
            "name": it.name,
            "slug": it.slug,
            "category": getattr(it.category, 'name', None),
            "supplier": getattr(it.supplier, 'name', None),
            "stock_level": it.stock_level,
            "min_stock": it.min_stock,
            "max_stock": it.max_stock,
            "status": it.status,
            "total_value": round(it.total_value or 0, 2)
        })

    return Response({"low_items_count": qs.count(), "items": items})
