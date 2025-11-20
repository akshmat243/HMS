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

from rest_framework import permissions
from .models import SidebarApp
from .serializers import SidebarAppSerializer

class SidebarAppViewSet(ProtectedModelViewSet):
    queryset = SidebarApp.objects.all().order_by('order')
    serializer_class = SidebarAppSerializer
    model_name = 'SidebarApp'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # Superuser sees all active apps
        if user.is_superuser:
            return qs

        user_role = getattr(user, 'role', None)
        if user_role:
            # Filter apps by roles_allowed containing user's role name (case-insensitive)
            return qs.filter(roles_allowed__icontains=user_role.name)
        else:
            return qs.none()
