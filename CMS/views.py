from MBP.views import ProtectedModelViewSet
from .models import Page, FAQ, Banner, MetaTag
from .serializers import PageSerializer, FAQSerializer, BannerSerializer, MetaTagSerializer

class PageViewSet(ProtectedModelViewSet):
    queryset = Page.objects.all()
    serializer_class = PageSerializer
    model_name = 'Page'
    lookup_field = 'slug'


class FAQViewSet(ProtectedModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
    model_name = 'FAQ'
    lookup_field = 'slug'


class BannerViewSet(ProtectedModelViewSet):
    queryset = Banner.objects.all()
    serializer_class = BannerSerializer
    model_name = 'Banner'
    lookup_field = 'slug'


class MetaTagViewSet(ProtectedModelViewSet):
    queryset = MetaTag.objects.select_related('page').all()
    serializer_class = MetaTagSerializer
    model_name = 'MetaTag'
    lookup_field = 'slug'
