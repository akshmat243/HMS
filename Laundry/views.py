from MBP.views import ProtectedModelViewSet
from .models import LaundryService, LaundryOrder
from .serializers import LaundryServiceSerializer, LaundryOrderSerializer


class LaundryServiceViewSet(ProtectedModelViewSet):
    queryset = LaundryService.objects.all()
    serializer_class = LaundryServiceSerializer
    model_name = 'LaundryService'
    lookup_field = 'slug'


class LaundryOrderViewSet(ProtectedModelViewSet):
    queryset = LaundryOrder.objects.all()
    serializer_class = LaundryOrderSerializer
    model_name = 'LaundryOrder'
    lookup_field = 'id'

    def perform_create(self, serializer):
        instance = serializer.save()

        service = instance.service
        if service:
            if service.rate_type == 'per_kg' and instance.weight:
                instance.total_price = service.rate * instance.weight
            elif service.rate_type == 'per_piece' and instance.quantity:
                instance.total_price = service.rate * instance.quantity
            instance.save()

    def perform_update(self, serializer):
        instance = serializer.save()

        service = instance.service
        if service:
            if service.rate_type == 'per_kg' and instance.weight:
                instance.total_price = service.rate * instance.weight
            elif service.rate_type == 'per_piece' and instance.quantity:
                instance.total_price = service.rate * instance.quantity
            instance.save()
