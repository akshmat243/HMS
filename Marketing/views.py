from MBP.views import ProtectedModelViewSet
from .models import Campaign, Promotion
from .serializers import CampaignSerializer, PromotionSerializer

class CampaignViewSet(ProtectedModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    model_name = 'Campaign'
    lookup_field = 'slug'


class PromotionViewSet(ProtectedModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    model_name = 'Promotion'
    lookup_field = 'slug'
