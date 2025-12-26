from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Avg
from .models import Campaign, CampaignEvent, Promotion 
from .serializers import CampaignSerializer ,  CampaignEventSerializer
from MBP.views import ProtectedModelViewSet
from .serializers import PromotionSerializer
from rest_framework.decorators import action
from rest_framework.views import APIView
from django.utils import timezone
from django.core.exceptions import FieldError
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from django.apps import apps
from django.db.models import Sum
from datetime import timedelta
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, NotFound
from Reviews.models import HotelReview
from django.db.models.functions import Coalesce

def _fmt_number(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return n
class CampaignViewSet(ProtectedModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    model_name = 'Campaign'
    lookup_field = 'slug'
    permission_classes = [IsAuthenticated]

    def _best_order_field(self):
        candidate_fields = ["-created_at", "-start_date", "-id"]
        for f in candidate_fields:
            raw = f.lstrip("-")
            if raw in [field.name for field in Campaign._meta.get_fields()]:
                return f
        return "-id"

    def get_queryset(self):
        """
        Role-aware queryset:
         - superuser -> all campaigns
         - admin -> campaigns for user's hotel only
         - others -> none
        """
        user = getattr(self.request, "user", None)
        order_by = self._best_order_field()
        base_qs = self.queryset.order_by(order_by)

        if not user or user.is_anonymous:
            return base_qs.none()

        if getattr(user, "is_superuser", False):
            return base_qs

        user_role = getattr(user, "role", None)
        role_name = None
        if user_role:
            role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)

        if role_name and role_name.lower() == "admin":
            user_hotel = getattr(user, "hotel", None)
            if user_hotel:
                if "hotel" in [f.name for f in Campaign._meta.get_fields()]:
                    return base_qs.filter(hotel=user_hotel)
            return base_qs.none()

        return base_qs.none()

    def perform_create(self, serializer):
        user = getattr(self.request, "user", None)
        if user and not getattr(user, "is_superuser", False):
            user_role = getattr(user, "role", None)
            role_name = None
            if user_role:
                role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)

            if role_name and role_name.lower() == "admin":
                user_hotel = getattr(user, "hotel", None)
                if user_hotel and not self.request.data.get("hotel"):
                    serializer.save(hotel=user_hotel)
                    return
        serializer.save()

    def _compute_metrics(self, obj):
        impressions = clicks = reach = 0
        try:
            rel = getattr(obj, 'events', None) or getattr(obj, 'campaignevent_set', None)
            if rel is not None:
                impressions = rel.filter(event_type='impression').count()
                clicks = rel.filter(event_type='click').count()
                try:
                    reach = rel.filter(event_type='impression').values('user_id').distinct().count()
                    if not reach:
                        reach = rel.filter(event_type='impression').values('session_id').distinct().count()
                except Exception:
                    reach = impressions
        except Exception:
            impressions = clicks = reach = 0

        engagement_rate = (clicks / impressions * 100) if impressions else 0
        return {
            "reach": _fmt_number(reach),
            "impressions": impressions,
            "clicks": clicks,
            "engagement": f"{round(engagement_rate, 1)}%"
        }

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        out = []
        for c in qs:
            m = self._compute_metrics(c)
            out.append({
                "slug": c.slug,
                "name": c.name,
                "type": dict(Campaign.CAMPAIGN_TYPE_CHOICES).get(c.type, c.type) if hasattr(Campaign, 'CAMPAIGN_TYPE_CHOICES') else c.type,
                "status": c.status,
                "reach": m["reach"],
                "engagement": m["engagement"],
                "start_date": str(c.start_date) if c.start_date else None,
                "end_date": str(c.end_date) if c.end_date else None,
                "budget": str(c.budget) if getattr(c, "budget", None) is not None else None,
            })
        return Response(out, status=status.HTTP_200_OK)

    def retrieve(self, request, slug=None, *args, **kwargs):
        obj = self.get_object()
        m = self._compute_metrics(obj)
        data = {
            "slug": obj.slug,
            "name": obj.name,
            "type": dict(Campaign.CAMPAIGN_TYPE_CHOICES).get(obj.type, obj.type) if hasattr(Campaign, 'CAMPAIGN_TYPE_CHOICES') else obj.type,
            "status": obj.status,
            "reach": m["reach"],
            "impressions": m["impressions"],
            "clicks": m["clicks"],
            "engagement": m["engagement"],
            "start_date": str(obj.start_date) if obj.start_date else None,
            "end_date": str(obj.end_date) if obj.end_date else None,
            "budget": str(obj.budget) if getattr(obj, "budget", None) is not None else None,
            "description": obj.description,
            "results": obj.results,
        }
        return Response(data, status=status.HTTP_200_OK)

    # ----------------- events action (correctly indented) -----------------
    @action(detail=True, methods=['post'], url_path='events', permission_classes=[IsAuthenticated])
    def events(self, request, slug=None):
        """
        POST /api/marketing/campaigns/<slug>/events/
        Body (JSON):
        {
            "event_type": "impression" | "click" | "conversion",
            "user_id": "optional",
            "session_id": "optional"
        }
        """
        event_type = request.data.get('event_type')
        if event_type not in ['impression', 'click', 'conversion']:
            return Response({"detail": "invalid event_type"}, status=status.HTTP_400_BAD_REQUEST)

        # enforces slug lookup + permission via get_object()
        campaign_obj = self.get_object()

        campaign_hotel = getattr(campaign_obj, "hotel", None)
        if campaign_hotel is None:
            return Response({"detail": "campaign has no hotel assigned"}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "event_type": event_type,
            "user_id": request.data.get("user_id"),
            "session_id": request.data.get("session_id"),
        }

        ser = CampaignEventSerializer(data=payload)
        ser.is_valid(raise_exception=True)

        ev = CampaignEvent.objects.create(
            campaign=campaign_obj,
            hotel=campaign_hotel,
            event_type=ser.validated_data.get("event_type"),
            user_id=ser.validated_data.get("user_id"),
            session_id=ser.validated_data.get("session_id"),
        )

        out_ser = CampaignEventSerializer(ev)
        return Response(out_ser.data, status=status.HTTP_201_CREATED)

    # ----------------- metrics action -----------------
    @action(detail=True, methods=['get'], url_path='metrics', permission_classes=[IsAuthenticated])
    def metrics(self, request, slug=None):
        campaign = self.get_object()
        rel = getattr(campaign, 'events', None) or getattr(campaign, 'campaignevent_set', None)
        events = rel.all() if rel is not None else CampaignEvent.objects.none()

        impressions = events.filter(event_type='impression').count()
        clicks = events.filter(event_type='click').count()
        conversions = events.filter(event_type='conversion').count()
        reach = events.values('session_id').distinct().count() if events is not None else 0

        engagement_rate = 0
        if impressions > 0:
            engagement_rate = round((clicks / impressions) * 100, 2)

        data = {
            "impressions": impressions,
            "clicks": clicks,
            "conversions": conversions,
            "reach": reach,
            "engagement_rate": f"{engagement_rate}%"
        }

        return Response(data, status=status.HTTP_200_OK)


class PromotionViewSet(viewsets.ModelViewSet):
    """
    Promotion viewset:
      - lookup via slug
      - role-aware queryset:
          superuser => all
          admin => promotions for user's hotel only
          others => none
      - if admin creates and doesn't pass hotel, we assign user's hotel automatically
    """
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    lookup_field = "slug"
    permission_classes = [IsAuthenticated]

    def _best_order_field(self):
        # prefer fields if present on model
        candidate_fields = ["-created_at", "-start_date", "-id"]
        for f in candidate_fields:
            raw = f.lstrip("-")
            if raw in [field.name for field in Promotion._meta.get_fields()]:
                return f
        return "-id"

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        order_by = self._best_order_field()
        base_qs = self.queryset.order_by(order_by)

        if not user or user.is_anonymous:
            return base_qs.none()

        # superuser -> all
        if getattr(user, "is_superuser", False):
            return base_qs

        # determine role name safely
        user_role = getattr(user, "role", None)
        role_name = None
        if user_role:
            role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)

        # admin -> only promotions for user's hotel
        if role_name and role_name.lower() == "admin":
            user_hotel = getattr(user, "hotel", None)
            if user_hotel:
                # ensure Promotion has hotel field
                if "hotel" in [f.name for f in Promotion._meta.get_fields()]:
                    return base_qs.filter(hotel=user_hotel)
            return base_qs.none()

        # default -> no access
        return base_qs.none()

    def perform_create(self, serializer):
        """
        If admin creating and doesn't provide hotel, attach user's hotel automatically.
        If request.user is superuser, allow whatever hotel provided in payload.
        """
        user = getattr(self.request, "user", None)

        # if user is admin and hotel not provided, set it from user
        if user and not getattr(user, "is_superuser", False):
            user_role = getattr(user, "role", None)
            role_name = None
            if user_role:
                role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)

            if role_name and role_name.lower() == "admin":
                user_hotel = getattr(user, "hotel", None)
                # if no hotel in payload, set it
                if user_hotel and not self.request.data.get("hotel"):
                    serializer.save(hotel=user_hotel)
                    return

        # default save (superuser or payload contained hotel)
        serializer.save()

class MarketingAnalyticsAPIView(APIView):
    """
    GET /api/marketing/analytics/
    Query params:
      - campaign=<campaign-slug>    (slug only; NO ids)
      - period=YYYY-MM              (takes precedence over year/month)
      - year=<YYYY>&month=<M>       (must supply both)
      - raw=true                    (include raw previous/current counts)

    Access rules:
      - superuser -> can query any campaign or global analytics
      - admin (user.role.name == "admin") -> can query only campaigns for user's hotel (or global if no campaign param)
      - other authenticated users -> forbidden
    """
    permission_classes = [IsAuthenticated]

    # date fields to try on CampaignEvent model
    def _get_field_candidates(self):
        return ["timestamp", "created_at", "date"]

    def get_campaign_queryset(self, user):
        """
        Return Campaign queryset visible to user.
        - superuser -> all campaigns
        - admin -> campaigns belonging to user's hotel
        - others -> raise PermissionDenied when they try to access global analytics
        """
        if not user or user.is_anonymous:
            raise NotAuthenticated("authentication required")
        if getattr(user, "is_superuser", False):
            return Campaign.objects.all()
        user_role = getattr(user, "role", None)
        role_name = None
        if user_role:
            role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)
        if role_name and role_name.lower() == "admin":
            user_hotel = getattr(user, "hotel", None)
            if not user_hotel:
                # admin without a hotel -> no campaigns
                return Campaign.objects.none()
            return Campaign.objects.filter(hotel=user_hotel)
        # other roles not allowed to query global analytics
        raise PermissionDenied("forbidden")

    def _count_events_for_month(self, event_type_value, year, month, campaign_obj=None, campaign_qs=None):
        """
        Count events for a specific year/month and event type.
        If campaign_obj provided, filter by that campaign.
        If campaign_qs provided, filter events for campaigns in that queryset.
        """
        qs = CampaignEvent.objects.all()
        if campaign_obj is not None:
            qs = qs.filter(campaign=campaign_obj)
        elif campaign_qs is not None:
            qs = qs.filter(campaign__in=campaign_qs)

        last_error = None
        for f in self._get_field_candidates():
            try:
                kwargs = {
                    f + "__year": year,
                    f + "__month": month,
                    "event_type": event_type_value,
                }
                return qs.filter(**kwargs).count()
            except FieldError as fe:
                last_error = fe
                continue
            except Exception:
                # continue trying other fields
                last_error = last_error or None
                continue
        raise last_error or FieldError("No suitable date field found on CampaignEvent (checked: timestamp, created_at, date)")

    def calculate_growth(self, current, previous):
        try:
            previous = float(previous)
            current = float(current)
        except Exception:
            if previous == 0:
                return f"+{int(current) * 100}%" if current > 0 else "0%"
            return "0%"
        if previous == 0:
            if current > 0:
                return f"+{int(current * 100)}%"
            return "0%"
        change = ((current - previous) / previous) * 100.0
        sign = "+" if change >= 0 else ""
        return f"{sign}{round(change, 1)}%"

    def _resolve_campaign_by_slug(self, slug):
        if not slug:
            return None
        try:
            return Campaign.objects.get(slug=slug)
        except Campaign.DoesNotExist:
            raise NotFound(detail="campaign not found")

    def _assert_user_can_access_campaign(self, user, campaign):
        if not user or user.is_anonymous:
            raise NotAuthenticated(detail="authentication required")
        if getattr(user, "is_superuser", False):
            return None
        user_role = getattr(user, "role", None)
        role_name = None
        if user_role:
            role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)
        if role_name and role_name.lower() == "admin":
            user_hotel = getattr(user, "hotel", None)
            if user_hotel and getattr(campaign, "hotel", None) == user_hotel:
                return None
            raise PermissionDenied(detail="forbidden: campaign not in your hotel")
        raise PermissionDenied(detail="forbidden")

    def get(self, request, *args, **kwargs):
        campaign_slug = request.query_params.get("campaign")
        period = request.query_params.get("period")
        year_q = request.query_params.get("year")
        month_q = request.query_params.get("month")
        raw_flag = request.query_params.get("raw", "false").lower() in ("1", "true", "yes")

        # Resolve campaign if slug given (slug-only)
        campaign_obj = None
        if campaign_slug:
            campaign_obj = self._resolve_campaign_by_slug(campaign_slug)
            # enforce per-campaign access rules
            self._assert_user_can_access_campaign(request.user, campaign_obj)
            campaign_qs = None
        else:
            # No slug -> use user's campaign queryset (global analytics subject to role)
            try:
                campaign_qs = self.get_campaign_queryset(request.user)
            except (NotAuthenticated, PermissionDenied) as e:
                # non-admin/non-superuser not allowed to get global analytics
                return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
            campaign_obj = None

        # parse period/year-month (validation)
        today = timezone.now().date()
        try:
            if period:
                parts = period.split("-")
                if len(parts) != 2:
                    return Response({"detail": "period must be in YYYY-MM format"}, status=status.HTTP_400_BAD_REQUEST)
                y = int(parts[0]); m = int(parts[1])
                if m < 1 or m > 12:
                    return Response({"detail": "month must be between 1 and 12"}, status=status.HTTP_400_BAD_REQUEST)
                if not (1970 <= y <= today.year + 1):
                    return Response({"detail": "year out of allowed range"}, status=status.HTTP_400_BAD_REQUEST)
                cur_year, cur_month = y, m
            elif year_q or month_q:
                if not (year_q and month_q):
                    return Response({"detail": "both year and month must be provided together"}, status=status.HTTP_400_BAD_REQUEST)
                cur_year = int(year_q); cur_month = int(month_q)
                if cur_month < 1 or cur_month > 12:
                    return Response({"detail": "month must be between 1 and 12"}, status=status.HTTP_400_BAD_REQUEST)
                if not (1970 <= cur_year <= today.year + 1):
                    return Response({"detail": "year out of allowed range"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                cur_year, cur_month = today.year, today.month
        except ValueError:
            return Response({"detail": "invalid numeric values for period/year/month"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "invalid period/year/month"}, status=status.HTTP_400_BAD_REQUEST)

        # prev month/year
        if cur_month == 1:
            prev_month, prev_year = 12, cur_year - 1
        else:
            prev_month, prev_year = cur_month - 1, cur_year

        IMPRESSION = "impression"
        CLICK = "click"

        try:
            impressions_current = self._count_events_for_month(IMPRESSION, cur_year, cur_month, campaign_obj=campaign_obj, campaign_qs=locals().get('campaign_qs'))
            impressions_previous = self._count_events_for_month(IMPRESSION, prev_year, prev_month, campaign_obj=campaign_obj, campaign_qs=locals().get('campaign_qs'))

            clicks_current = self._count_events_for_month(CLICK, cur_year, cur_month, campaign_obj=campaign_obj, campaign_qs=locals().get('campaign_qs'))
            clicks_previous = self._count_events_for_month(CLICK, prev_year, prev_month, campaign_obj=campaign_obj, campaign_qs=locals().get('campaign_qs'))
        except FieldError:
            return Response({"detail": "Date field not found. Expected one of: timestamp, created_at, date."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except NotFound as nf:
            return Response({"detail": str(nf)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response({"detail": "unexpected error calculating analytics", "error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def compute_ctr(clicks, imps):
            if imps == 0:
                return 0.0
            return round((clicks / imps) * 100.0, 1)

        ctr_current = compute_ctr(clicks_current, impressions_current)
        ctr_previous = compute_ctr(clicks_previous, impressions_previous)

        impressions_improvement = self.calculate_growth(impressions_current, impressions_previous)
        ctr_improvement = self.calculate_growth(ctr_current, ctr_previous)

        period_label = f"{cur_year:04d}-{cur_month:02d}"
        data = {
            #"period": period_label,
            "total_impressions": impressions_current,
            "impressions_improvement": impressions_improvement,
            "click_through_rate": f"{ctr_current}%",
            "ctr_improvement": ctr_improvement,
        }

        if raw_flag:
            data.update({
                "impressions_current": impressions_current,
                "impressions_previous": impressions_previous,
                "clicks_current": clicks_current,
                "clicks_previous": clicks_previous,
            })

        return Response(data, status=status.HTTP_200_OK)


def safe_percent(numer, denom, decimals=1):
    if denom == 0:
        return 0.0
    return round((numer / denom) * 100.0, decimals)



def calculate_growth(current, previous):
    """
    Growth rule (used for counts/money/conversion % growth):
      - if previous == 0 and current > 0 => +{current*100}%  (e.g. prev=0 cur=2 -> +200%)
      - if both zero => "0%"
      - else => signed percent rounded to 1 decimal (e.g. +22.0%)
    Returns a string like "+22.0%" or "0%".
    """
    try:
        cur = float(current)
        prev = float(previous)
    except Exception:
        return "0%"

    if prev == 0:
        if cur > 0:
            return f"+{int(cur * 100)}%"
        return "0%"
    change = ((cur - prev) / prev) * 100.0
    sign = "+" if change >= 0 else ""
    return f"{sign}{round(change, 1)}%"

def calculate_count_diff_int(current, previous):
    """
    Return signed integer difference for counts (active campaigns) as an INT.
    Example: current=8, previous=6 -> returns 2
             current=5, previous=7 -> returns -2
             current=3, previous=3 -> returns 0
    """
    try:
        cur = int(current)
        prev = int(previous)
    except Exception:
        return 0
    return cur - prev

def try_date_field_filter(qs, year=None, month=None, start=None, end=None):
    """
    Try filtering by common date fields.
    """
    date_fields = ["created_at", "timestamp", "date"]
    last_err = None
    for f in date_fields:
        try:
            if start is not None and end is not None:
                return qs.filter({f + "_gte": start, f + "_lte": end})
            if year is not None and month is not None:
                return qs.filter({f + "_year": year, f + "_month": month})
        except FieldError as fe:
            last_err = fe
            continue
    raise last_err or FieldError("No suitable date field found")

class MarketingOverviewAPIView(APIView):
    """
    Overview metrics endpoint.
    Optional query params:
      - campaign=<campaign-slug>   (filter overview to a single campaign by slug; NO ids)
      - period_start=YYYY-MM-DD
      - period_end=YYYY-MM-DD
    Role rules:
      - superuser -> global or campaign-specific
      - admin -> only campaigns for user's hotel (or campaign in their hotel)
      - others -> forbidden
    """
    permission_classes = [IsAuthenticated]

    def _get_marketing_transaction_model(self):
        candidates = [
            ("Marketing", "MarketingTransaction"),
            ("marketing", "MarketingTransaction"),
            ("Finance", "MarketingTransaction"),
            ("finance", "MarketingTransaction"),
        ]
        for app, model in candidates:
            try:
                return apps.get_model(app, model)
            except Exception:
                continue
        return None

    def get_campaign_queryset_for_user(self, user):
        if not user or user.is_anonymous:
            raise NotAuthenticated("authentication required")
        if getattr(user, "is_superuser", False):
            return Campaign.objects.all()
        user_role = getattr(user, "role", None)
        role_name = None
        if user_role:
            role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)
        if role_name and role_name.lower() == "admin":
            user_hotel = getattr(user, "hotel", None)
            if not user_hotel:
                return Campaign.objects.none()
            return Campaign.objects.filter(hotel=user_hotel)
        raise PermissionDenied("forbidden")

    def _resolve_campaign_by_slug(self, slug):
        if not slug:
            return None
        try:
            return Campaign.objects.get(slug=slug)
        except Campaign.DoesNotExist:
            raise PermissionDenied("campaign not found or access denied")

    def get(self, request, *args, **kwargs):
        today = timezone.now().date()

        # optional filters
        campaign_slug = request.query_params.get("campaign")
        period_start = request.query_params.get("period_start")
        period_end = request.query_params.get("period_end")

        # validate optional period range if provided
        start_date = end_date = None
        if period_start or period_end:
            if not (period_start and period_end):
                return Response({"detail": "both period_start and period_end must be provided together"}, status=400)
            try:
                from django.utils.dateparse import parse_date
                start_date = parse_date(period_start)
                end_date = parse_date(period_end)
                if not start_date or not end_date:
                    return Response({"detail": "invalid date format, expected YYYY-MM-DD"}, status=400)
                if start_date > end_date:
                    return Response({"detail": "period_start cannot be after period_end"}, status=400)
            except Exception:
                return Response({"detail": "invalid date range"}, status=400)

        # resolve campaign or campaign queryset according to role
        campaign_obj = None
        try:
            if campaign_slug:
                campaign_obj = Campaign.objects.filter(slug=campaign_slug).first()
                if not campaign_obj:
                    return Response({"detail": "campaign not found"}, status=404)
                # enforce role access: reuse get_campaign_queryset_for_user
                # if user isn't allowed to see the campaign, forbid
                user_campaign_qs = self.get_campaign_queryset_for_user(request.user)
                if campaign_obj not in user_campaign_qs:
                    return Response({"detail": "forbidden: campaign not in your scope"}, status=403)
                campaign_qs = None
            else:
                campaign_qs = self.get_campaign_queryset_for_user(request.user)
        except NotAuthenticated as e:
            return Response({"detail": str(e)}, status=401)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=403)

        # ---------------- Active campaigns (snapshot)
        try:
            check_date = today
            if campaign_obj:
                active_current = Campaign.objects.filter(slug=campaign_obj.slug, status="active", start_date__lte=check_date, end_date__gte=check_date).count()
            else:
                active_current = campaign_qs.filter(status="active", start_date__lte=check_date, end_date__gte=check_date).count()
        except Exception:
            active_current = 0

        snapshot_prev_day = today - timedelta(days=7)
        try:
            if campaign_obj:
                active_previous = Campaign.objects.filter(slug=campaign_obj.slug, status="active", start_date__lte=snapshot_prev_day, end_date__gte=snapshot_prev_day).count()
            else:
                active_previous = campaign_qs.filter(status="active", start_date__lte=snapshot_prev_day, end_date__gte=snapshot_prev_day).count()
        except Exception:
            active_previous = 0

        active_campaigns_improvement = active_current - active_previous

        # ---------------- Email open rate (month vs previous month)
        cur_year, cur_month = today.year, today.month
        if cur_month == 1:
            prev_year, prev_month = cur_year - 1, 12
        else:
            prev_year, prev_month = cur_year, cur_month - 1

        base_events = CampaignEvent.objects.all()
        if campaign_obj:
            base_events = base_events.filter(campaign=campaign_obj)
        else:
            base_events = base_events.filter(campaign__in=campaign_qs)

        # use created_at filtering (exists in model)
        delivered_current = base_events.filter(campaign__type="email", event_type="impression", created_at__year=cur_year, created_at__month=cur_month).count()
        opens_current = base_events.filter(campaign__type="email", event_type="click", created_at__year=cur_year, created_at__month=cur_month).count()
        delivered_previous = base_events.filter(campaign__type="email", event_type="impression", created_at__year=prev_year, created_at__month=prev_month).count()
        opens_previous = base_events.filter(campaign__type="email", event_type="click", created_at__year=prev_year, created_at__month=prev_month).count()

        email_rate_current = safe_percent(opens_current, delivered_current)
        email_rate_previous = safe_percent(opens_previous, delivered_previous)
        email_rate_improvement = calculate_growth(email_rate_current, email_rate_previous)

        # ---------------- Conversion rate (month vs previous month)
        conversions_current = base_events.filter(event_type="conversion", created_at__year=cur_year, created_at__month=cur_month).count()
        impressions_current = base_events.filter(event_type="impression", created_at__year=cur_year, created_at__month=cur_month).count()
        conversions_previous = base_events.filter(event_type="conversion", created_at__year=prev_year, created_at__month=prev_month).count()
        impressions_previous = base_events.filter(event_type="impression", created_at__year=prev_year, created_at__month=prev_month).count()

        conv_rate_current = safe_percent(conversions_current, impressions_current)
        conv_rate_previous = safe_percent(conversions_previous, impressions_previous)
        conv_rate_improvement = calculate_growth(conv_rate_current, conv_rate_previous)

        # ---------------- Marketing ROI (last 15 days vs previous 15 days)
        MT = self._get_marketing_transaction_model()
        start_current = (start_date if start_date else (today - timedelta(days=14)))
        end_current = (end_date if end_date else today)
        start_prev = start_current - timedelta(days=(end_current - start_current).days + 1)
        end_prev = start_current - timedelta(days=1)

        roi_current = roi_previous = 0
        if MT:
            cur_qs = MT.objects.filter(created_at__gte=start_current, created_at__lte=end_current)
            prev_qs = MT.objects.filter(created_at__gte=start_prev, created_at__lte=end_prev)
            if campaign_obj:
                cur_qs = cur_qs.filter(campaign__slug=campaign_obj.slug)
                prev_qs = prev_qs.filter(campaign__slug=campaign_obj.slug)
            revenue_cur = cur_qs.filter(transaction_type="revenue").aggregate(Sum("amount"))["amount__sum"] or 0
            cost_cur = cur_qs.filter(transaction_type="cost").aggregate(Sum("amount"))["amount__sum"] or 0
            revenue_prev = prev_qs.filter(transaction_type="revenue").aggregate(Sum("amount"))["amount__sum"] or 0
            cost_prev = prev_qs.filter(transaction_type="cost").aggregate(Sum("amount"))["amount__sum"] or 0
            roi_current = revenue_cur - cost_cur
            roi_previous = revenue_prev - cost_prev

        def format_money(v):
            try:
                v = float(v)
            except Exception:
                return str(v)
            if abs(v) >= 1000:
                return f"${round(v/1000,1)}K"
            return f"${round(v,2)}"

        marketing_roi = format_money(roi_current)
        marketing_roi_improvement = calculate_growth(roi_current, roi_previous)

        data = {
            "active_campaigns": active_current,
            "active_campaigns_improvement": active_campaigns_improvement,
            "email_open_rate": f"{email_rate_current}%",
            "email_open_rate_improvement": email_rate_improvement,
            "conversion_rate": f"{conv_rate_current}%",
            "conversion_rate_improvement": conv_rate_improvement,
            "marketing_roi": marketing_roi,
            "marketing_roi_improvement": marketing_roi_improvement,
        }

        return Response(data, status=200)
    


class ReviewMetricsAPIView(APIView):
    """
    GET /api/marketing/reviews/metrics/
    Calculates Hotel Review metrics (Average Rating, Total Reviews, Positive Reviews %)
    based on the user's hotel scope (Admin) or globally (Superuser).
    Positive Review is defined as rating >= 4 (as rating is PositiveIntegerField 1-5).
    """
    permission_classes = [IsAuthenticated]
    
    def _get_hotel_review_queryset(self, user):
        """
        Role-aware queryset for HotelReview, similar to Campaign/Promotion access logic.
        """
        if HotelReview is None:
            raise NotFound("HotelReview model not found. Check imports.")
            
        if not user or user.is_anonymous:
            raise NotAuthenticated("Authentication required")
        
        # Superuser access
        if getattr(user, "is_superuser", False):
            return HotelReview.objects.all()

        # Admin access
        user_role = getattr(user, "role", None)
        role_name = None
        if user_role:
            role_name = getattr(user_role, "name", None) or (user_role if isinstance(user_role, str) else None)
        
        if role_name and role_name.lower() == "admin":
            user_hotel = getattr(user, "hotel", None)
            if user_hotel:
                # Filter reviews only for the admin's hotel
                return HotelReview.objects.filter(hotel=user_hotel)
            # Admin without a hotel can see no reviews
            return HotelReview.objects.none()

        # Other authenticated users are forbidden
        raise PermissionDenied("Forbidden: Insufficient permissions to view review metrics")


    def get(self, request, *args, **kwargs):
        if HotelReview is None:
             return Response({"detail": "Review feature is currently unavailable (Model not found)"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
             
        try:
            review_qs = self._get_hotel_review_queryset(request.user)
            total_reviews = review_qs.count()

            if total_reviews == 0:
                data = {
                    "average_rating": 0.0,
                    "total_reviews": 0,
                    "positive_reviews_percentage": "0%",
                }
                return Response(data, status=status.HTTP_200_OK)

            # 1. Average Rating Calculation
            avg_rating = review_qs.aggregate(
                avg_r=Coalesce(Avg('rating'), 0.0)
            )['avg_r']
            
            # 2. Positive Reviews Count (Rating >= 4 for 3.8+ threshold on 1-5 integer scale)
            positive_reviews_count = review_qs.filter(rating__gte=4).count()
            
            # 3. Positive Reviews Percentage
            positive_percent = (positive_reviews_count / total_reviews) * 100
            
            # Final Data Structure
            data = {
                # Format to one decimal place (e.g., 4.8)
                "average_rating": round(avg_rating, 1),
                # Total Count (e.g., 248)
                "total_reviews": total_reviews,
                # Percentage rounded to nearest integer with "%" (e.g., 95%)
                "positive_reviews_percentage": f"{round(positive_percent)}%",
            }

            return Response(data, status=status.HTTP_200_OK)

        except (NotAuthenticated, PermissionDenied, NotFound) as e:
            # Catch access errors and model not found errors
            status_code = status.HTTP_401_UNAUTHORIZED if isinstance(e, NotAuthenticated) else status.HTTP_403_FORBIDDEN
            status_code = status.HTTP_404_NOT_FOUND if isinstance(e, NotFound) else status_code
            return Response({"detail": str(e)}, status=status_code)
        
        except Exception as e:
            return Response({"detail": "An unexpected error occurred during review calculation", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)