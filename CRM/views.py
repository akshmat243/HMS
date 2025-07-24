from MBP.views import ProtectedModelViewSet
from .models import Lead, Customer, Interaction
from .serializers import LeadSerializer, CustomerSerializer, InteractionSerializer


class LeadViewSet(ProtectedModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    model_name = 'Lead'
    lookup_field = 'slug'


class CustomerViewSet(ProtectedModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    model_name = 'Customer'
    lookup_field = 'slug'


class InteractionViewSet(ProtectedModelViewSet):
    queryset = Interaction.objects.all()
    serializer_class = InteractionSerializer
    model_name = 'Interaction'
    lookup_field = 'id'
