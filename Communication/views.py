from MBP.views import ProtectedModelViewSet
from .models import Notification, Message, Feedback, Subscriber, OutgoingMessage, MessageTemplate
from .serializers import (
    NotificationSerializer, 
    MessageSerializer, 
    FeedbackSerializer, 
    NewsletterSerializer,
    MessageTemplateSerializer,
    OutgoingMessageSerializer,
    UseTemplateSerializer # Assuming this exists based on your original code usage
)
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from .utils import send_newsletter
from django.core.mail import send_mail
from django.conf import settings
from twilio.rest import Client
import os
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from Hotel.models import Hotel
from urllib.parse import quote_plus
import threading, logging
from django.utils import timezone


# ==============================================================================
# 1. HELPER FUNCTIONS (Kept global to ensure logic stays identical)
# ==============================================================================

def user_is_hotel_admin(user):
    """
    Allow if user is superuser, staff, has role 'admin', or group 'hotel_admin'.
    """
    if not user or not user.is_authenticated:
        return False

    if getattr(user, 'is_superuser', False):
        return True

    if getattr(user, 'is_staff', False):
        return True

    try:
        if hasattr(user, 'role') and user.role and getattr(user.role, 'name', '').lower() == 'admin':
            return True
    except Exception:
        pass

    if user.groups.filter(name='hotel_admin').exists():
        return True

    if hasattr(user, 'is_hotel_admin') and getattr(user, 'is_hotel_admin'):
        return True

    return False

def _send_email(to_email, subject, body):
    """Uses Django send_mail. Returns True on success, False on failure."""
    try:
        send_mail(
            subject or '',
            body or '',
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            [to_email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        import logging
        logging.exception("Email send failed")
        return False

def _send_whatsapp(number, body):
    """
    number: 10 digits (e.g. '9876543210') OR full with country '91...' .
    We'll convert to E.164 WhatsApp format: 'whatsapp:+91xxxxxxxxxx'
    """
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_whatsapp = os.getenv('TWILIO_WHATSAPP_FROM')
        if not all([account_sid, auth_token, from_whatsapp]):
            raise Exception("Twilio credentials missing")

        client = Client(account_sid, auth_token)

        num = str(number)
        if len(num) == 10:
            to_whatsapp = f"whatsapp:+91{num}"
        elif num.startswith('+'):
            to_whatsapp = f"whatsapp:{num}"
        else:
            to_whatsapp = f"whatsapp:+{num}"

        message = client.messages.create(
            body = body or "",
            from_ = from_whatsapp,
            to = to_whatsapp
        )
        return True if getattr(message, 'sid', None) else False

    except Exception as e:
        import logging
        logging.exception("WhatsApp send failed")
        return False

def _send_sms(number, body):
    """Stub for SMS gateway."""
    return True

def _human_time_ago(dt):
    if not dt:
        return None
    now = timezone.now()
    diff = now - dt
    secs = diff.total_seconds()
    mins = secs // 60
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{int(mins)} minute{'s' if mins>1 else ''} ago"
    hours = mins // 60
    if hours < 24:
        return f"{int(hours)} hour{'s' if hours>1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{int(days)} day{'s' if days>1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{int(months)} month{'s' if months>1 else ''} ago"
    years = months // 12
    return f"{int(years)} year{'s' if years>1 else ''} ago"


# ==============================================================================
# 2. STANDARD VIEWSETS
# ==============================================================================

class NotificationViewSet(ProtectedModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    model_name = 'Notification'
    lookup_field = 'slug'


class FeedbackViewSet(ProtectedModelViewSet):
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    model_name = 'Feedback'
    lookup_field = 'slug'


# ==============================================================================
# 3. MESSAGE VIEWSET (Consolidated)
# ==============================================================================

class MessageViewSet(ProtectedModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    model_name = 'Message'
    lookup_field = 'slug'

    # --------------------------------------------------------------------------
    # ACTION: NEWSLETTER SUBSCRIBE (Public)
    # --------------------------------------------------------------------------
    @action(detail=False, methods=['get', 'post'], permission_classes=[AllowAny], url_path='newsletter')
    def newsletter(self, request):
        """
        Handles functionality formerly in NewsletterSubscribeView.
        """
        if request.method == 'GET':
            subs = Subscriber.objects.all()
            serializer = NewsletterSerializer(subs, many=True)
            return Response(serializer.data, status=200)

        if request.method == 'POST':
            email = request.data.get("email")

            if not email:
                return Response({"error": "Email is required."}, status=400)

            serializer = NewsletterSerializer(data=request.data)

            if serializer.is_valid():
                try:
                    subscriber = serializer.save()
                    # Send confirmation email
                    send_newsletter(email)

                    return Response(
                        {"message": "Subscribed successfully."},
                        status=status.HTTP_201_CREATED
                    )
                except Exception:
                    return Response(
                        {"error": "Email already subscribed."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            return Response(serializer.errors, status=400)

    # --------------------------------------------------------------------------
    # ACTION: QUICK SEND (Admin Only)
    # --------------------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='quick-send')
    def quick_send(self, request):
        """
        Logic formerly in QuickSendAPIView.
        """
        # 1) check admin
        if not user_is_hotel_admin(request.user):
            return Response({"detail": "Forbidden - not hotel admin."}, status=status.HTTP_403_FORBIDDEN)

        # 2) validate input
        serializer = OutgoingMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        channel = data.get('channel')
        recipient = data.get('recipient')
        subject = data.get('subject', '')
        body = data.get('message', '')
        save_template = data.get('save_template', False)
        schedule_at = data.get('schedule_at', None)

        # 3) create DB record (pending or scheduled)
        status_val = 'scheduled' if schedule_at else 'pending'
        outgoing = OutgoingMessage.objects.create(
            channel=channel,
            recipient=recipient,
            subject=subject,
            message=body,
            status=status_val,
            created_by=request.user
        )

        # 4) optionally save template
        if save_template:
            try:
                MessageTemplate.objects.create(
                    name=subject,
                    channel=channel,
                    subject=subject,
                    body=body,
                    created_by=request.user
                )
            except Exception:
                logging.exception("Could not save message template")

        # --- SCHEDULED HANDLING ---
        if schedule_at:
            now = timezone.now()
            delay = (schedule_at - now).total_seconds()
            if delay < 0:
                delay = 0

            def _delayed_task(outgoing_id):
                try:
                    m = OutgoingMessage.objects.get(id=outgoing_id)
                    # Email
                    if m.channel == 'email':
                        ok = _send_email(m.recipient, m.subject, m.message)
                        m.status = 'sent' if ok else 'failed'
                        if ok: m.sent_at = timezone.now()
                        m.save(update_fields=['status', 'sent_at'])
                        return
                    
                    # WhatsApp (Mark pending_click)
                    if m.channel == 'whatsapp':
                        try:
                            m.status = 'pending_click'
                        except Exception:
                            m.status = 'pending'
                        m.save(update_fields=['status'])
                        return

                    # SMS
                    if m.channel == 'sms':
                        ok = _send_sms(m.recipient, m.message)
                        m.status = 'sent' if ok else 'failed'
                        if ok: m.sent_at = timezone.now()
                        m.save(update_fields=['status', 'sent_at'])
                        return

                except Exception:
                    logging.exception("Scheduled send failed for %s", outgoing_id)

            t = threading.Timer(delay, _delayed_task, args=[str(outgoing.id)])
            t.daemon = True
            t.start()

            try:
                outgoing.schedule_at = schedule_at
                outgoing.status = 'scheduled'
                outgoing.save(update_fields=['schedule_at', 'status'])
            except Exception:
                logging.exception("Could not save schedule_at")

            return Response({"message": "Scheduled successfully.", "id": str(outgoing.id)}, status=status.HTTP_201_CREATED)

        # --- IMMEDIATE SEND ---
        try:
            if channel == 'email':
                sent_ok = _send_email(recipient, subject, body)
                if sent_ok:
                    outgoing.status = 'sent'
                    outgoing.sent_at = timezone.now()
                    outgoing.save(update_fields=['status', 'sent_at'])
                    return Response({"message": "Sent successfully.", "id": str(outgoing.id)}, status=status.HTTP_201_CREATED)
                else:
                    outgoing.status = 'failed'
                    outgoing.save(update_fields=['status'])
                    return Response({"error": "Failed to send."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            elif channel == "whatsapp":
                account_sid = os.getenv('TWILIO_ACCOUNT_SID')
                auth_token = os.getenv('TWILIO_AUTH_TOKEN')
                from_whatsapp = os.getenv('TWILIO_WHATSAPP_FROM')

                if account_sid and auth_token and from_whatsapp:
                    sent_ok = _send_whatsapp(recipient, body)
                else:
                    # FREE fallback -> click-to-chat URL
                    try:
                        num = ''.join([c for c in str(recipient) if c.isdigit()])
                        if len(num) == 10:
                            phone_param = "91" + num 
                        else:
                            phone_param = num.lstrip('+').lstrip('0')

                        text_param = quote_plus(body or "")
                        click_url = f"https://api.whatsapp.com/send?phone={phone_param}&text={text_param}"

                        outgoing.status = 'pending'
                        outgoing.save(update_fields=['status'])

                        return Response({
                            "message": "Click URL generated. Open to send in WhatsApp.",
                            "click_url": click_url,
                            "id": str(outgoing.id)
                        }, status=status.HTTP_201_CREATED)
                    except Exception:
                        logging.exception("WhatsApp click-url generation failed")
                        sent_ok = False

                # Handle Twilio result if we didn't fallback
                if 'sent_ok' in locals() and sent_ok:
                    outgoing.status = 'sent'
                    outgoing.sent_at = timezone.now()
                    outgoing.save(update_fields=['status', 'sent_at'])
                    return Response({"message": "Sent successfully.", "id": str(outgoing.id)}, status=status.HTTP_201_CREATED)
                
                # If we fell through to here
                if outgoing.status != 'pending':
                    outgoing.status = 'failed'
                    outgoing.save(update_fields=['status'])
                    return Response({"error": "Failed to send/prepare WhatsApp."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            elif channel == 'sms':
                sent_ok = _send_sms(recipient, body)
                if sent_ok:
                    outgoing.status = 'sent'
                    outgoing.sent_at = timezone.now()
                    outgoing.save(update_fields=['status', 'sent_at'])
                    return Response({"message": "Sent successfully.", "id": str(outgoing.id)}, status=status.HTTP_201_CREATED)
                else:
                    outgoing.status = 'failed'
                    outgoing.save(update_fields=['status'])
                    return Response({"error": "Failed to send."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            else:
                outgoing.status = 'failed'
                outgoing.save(update_fields=['status'])
                return Response({"error": "Invalid channel."}, status=status.HTTP_400_BAD_REQUEST)

        except Exception:
            outgoing.status = 'failed'
            outgoing.save(update_fields=['status'])
            logging.exception("Exception while sending message")
            return Response({"error": "Exception while sending."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --------------------------------------------------------------------------
    # ACTION: OVERVIEW (Stats)
    # --------------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='overview')
    def overview(self, request):
        """
        Logic formerly in CommunicationOverviewAPIView.
        """
        user = request.user
        
        # Internal helper for this action
        def _get_overview_queryset(u):
            if u.is_superuser:
                return OutgoingMessage.objects.all()
            try:
                hotel = Hotel.objects.filter(owner=u).first()
                if hotel:
                    return OutgoingMessage.objects.filter(created_by__staff_profile__hotel=hotel) | OutgoingMessage.objects.filter(created_by__hotel=hotel)
            except Exception:
                pass
            try:
                if hasattr(u, "staff_profile") and getattr(u.staff_profile, "hotel", None):
                    h = u.staff_profile.hotel
                    return OutgoingMessage.objects.filter(created_by__staff_profile__hotel=h) | OutgoingMessage.objects.filter(created_by__hotel=h)
            except Exception:
                pass
            return OutgoingMessage.objects.filter(created_by=u)

        base_qs = _get_overview_queryset(user)

        sent_qs = base_qs.filter(status='sent')
        messages_sent = sent_qs.count()

        email_attempted = base_qs.filter(channel='email').count()
        email_sent = base_qs.filter(channel='email', status='sent').count()
        email_delivered_percent = (email_sent / email_attempted * 100) if email_attempted > 0 else 0.0

        whatsapp_sent = base_qs.filter(channel='whatsapp', status='sent').count()

        sms_attempted = base_qs.filter(channel='sms').count()
        sms_sent = base_qs.filter(channel='sms', status='sent').count()
        sms_delivered_percent = (sms_sent / sms_attempted * 100) if sms_attempted > 0 else 0.0

        return Response({
            "messages_sent": messages_sent,
            "email_delivered": f"{round(email_delivered_percent, 1)}%",
            "whatsapp_sent": whatsapp_sent,
            "sms_delivered": f"{round(sms_delivered_percent, 1)}%"
        })

    # --------------------------------------------------------------------------
    # ACTION: RECENT COMMUNICATIONS (Pagination)
    # --------------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='recent')
    def recent_communications(self, request):
        """
        Logic formerly in RecentCommunicationsAPIView.
        """
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        # Internal helper for this action
        def _get_recent_q(u):
            if getattr(u, "is_superuser", False):
                return Q()
            q = Q(created_by=u)
            try:
                q = q | Q(created_by__hotel__owner=u)
            except Exception:
                pass
            return q

        try:
            offset = int(request.query_params.get("offset", 0))
        except Exception:
            offset = 0
        try:
            limit = int(request.query_params.get("limit", 4))
        except Exception:
            limit = 4

        if offset < 0: offset = 0
        if limit <= 0: limit = 4
        if limit > 100: limit = 100

        user_q = _get_recent_q(user)
        qs = OutgoingMessage.objects.filter(user_q).order_by("-created_at")
        total = qs.count()

        items_qs = qs[offset : offset + limit]

        items = []
        for m in items_qs:
            created_at = getattr(m, "created_at", None)
            sent_at = getattr(m, "sent_at", None)
            items.append({
                "id": str(m.id),
                "slug": getattr(m, "slug", "") or "",
                "channel": getattr(m, "channel", "") or "",
                "recipient": getattr(m, "recipient", "") or "",
                "subject": getattr(m, "subject", "") or "",
                "message": getattr(m, "message", "") or "",
                "status": getattr(m, "status", "") or "",
                "created_at": created_at.isoformat() if created_at else None,
                "sent_at": sent_at.isoformat() if sent_at else None,
                "time_ago": _human_time_ago(sent_at or created_at),
            })

        next_offset = offset + len(items)
        has_more = next_offset < total
        
        return Response({
            "total_count": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset if has_more else None,
            "has_more": bool(has_more),
            "items": items
        }, status=200)

    # --------------------------------------------------------------------------
    # ACTION: TEMPLATES LIST
    # --------------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='templates')
    def list_templates(self, request):
        """
        Logic formerly in MessageTemplateListAPIView.
        """
        user = request.user
        if not user_is_hotel_admin(user):
            return Response({"detail": "Forbidden"}, status=403)

        if user.is_superuser:
            qs = MessageTemplate.objects.all().order_by('-created_at')
        else:
            qs = MessageTemplate.objects.filter(created_by=user).order_by('-created_at')
            if not qs.exists():
                try:
                    qs = MessageTemplate.objects.filter(created_by__hotel__owner=user).order_by('-created_at')
                except Exception:
                    qs = MessageTemplate.objects.filter(created_by=user).order_by('-created_at')

        serializer = MessageTemplateSerializer(qs, many=True)
        return Response(serializer.data, status=200)

    # --------------------------------------------------------------------------
    # ACTION: TEMPLATE DETAIL / MANAGE
    # --------------------------------------------------------------------------
    @action(detail=False, methods=['get', 'post'], url_path='manage-template')
    def manage_template(self, request):
        """
        Expects query param ?slug=<identifier> to target specific template.
        """
        user = request.user
        if not user_is_hotel_admin(user):
            return Response({"detail":"Forbidden"}, status=403)

        identifier = request.query_params.get('slug')
        if not identifier:
            return Response({"detail": "Slug query parameter required"}, status=400)

        template = get_object_or_404(MessageTemplate, slug=identifier)

        # GET Template Detail
        if request.method == 'GET':
            return Response({
                "id": str(template.id),
                "slug": template.slug or "",
                "name": template.name,
                "channel": template.channel,
                "subject": template.subject,
                "message": template.body,
                "created_time": template.created_at.isoformat() if template.created_at else None,
            }, status=200)

        # POST: Update or Send
        if request.method == 'POST':
            ser = UseTemplateSerializer(data=request.data, context={"channel": template.channel})
            if not ser.is_valid():
                return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
            data = ser.validated_data

            recipient = data.get("recipient")
            new_subject = data.get("subject", template.subject)
            new_body = data.get("message", template.body)
            send_flag = data.get("send", False)
            schedule_at = data.get("schedule_at", None)

            # Update template if changed
            changed = False
            if new_subject != template.subject:
                template.subject = new_subject
                changed = True
            if new_body != template.body:
                template.body = new_body
                changed = True
            if changed:
                try:
                    template.updated_at = timezone.now()
                    template.save(update_fields=['subject','body','updated_at'])
                except Exception:
                    template.save()

            # If not sending, just return
            if not send_flag and not schedule_at:
                return Response({"message":"Template updated (not sent).", "template_id": str(template.id)}, status=200)

            # Create outgoing record
            status_val = 'scheduled' if schedule_at else 'pending'
            
            # --- MODIFICATION HERE ---
            # We explicitly pass 'template_used=template' so the count increases
            outgoing = OutgoingMessage.objects.create(
                channel = template.channel,
                recipient = recipient,
                subject = new_subject,
                message = new_body,
                status = status_val,
                created_by = user,
                template_used = template  # <--- THIS LINKS IT FOR THE COUNT
            )

            # Scheduled logic
            if schedule_at:
                try:
                    outgoing.schedule_at = schedule_at
                    outgoing.status = 'scheduled'
                    outgoing.save(update_fields=['schedule_at','status'])
                except Exception:
                    outgoing.save()
                return Response({"message":"Scheduled successfully.", "id": str(outgoing.id)}, status=201)

            # Immediate Send Logic (Code remains same as before, just included for context)
            channel = template.channel or "email"

            # EMAIL
            if channel == "email":
                sent_ok = _send_email(recipient, new_subject, new_body)
                if sent_ok:
                    outgoing.status = 'sent'
                    outgoing.sent_at = timezone.now()
                    outgoing.save(update_fields=['status','sent_at'])
                    return Response({"message":"Sent successfully.", "id": str(outgoing.id)}, status=201)
                outgoing.status = 'failed'
                outgoing.save(update_fields=['status'])
                return Response({"error":"Failed to send."}, status=500)

            # WHATSAPP
            if channel == "whatsapp":
                account_sid = os.getenv('TWILIO_ACCOUNT_SID')
                auth_token = os.getenv('TWILIO_AUTH_TOKEN')
                from_whatsapp = os.getenv('TWILIO_WHATSAPP_FROM')

                if account_sid and auth_token and from_whatsapp:
                    try:
                        sent_ok = _send_whatsapp(recipient, new_body)
                    except Exception:
                        sent_ok = False
                    
                    if sent_ok:
                        outgoing.status = 'sent'
                        outgoing.sent_at = timezone.now()
                        outgoing.save(update_fields=['status','sent_at'])
                        return Response({"message":"Sent successfully.", "id": str(outgoing.id)}, status=201)
                    
                    outgoing.status = 'failed'
                    outgoing.save(update_fields=['status'])
                    return Response({"error":"Failed to send via Twilio."}, status=500)
                
                # FREE fallback
                try:
                    num = ''.join([c for c in str(recipient) if c.isdigit()])
                    if len(num) == 10:
                        phone_param = "91" + num 
                    else:
                        phone_param = num.lstrip('+').lstrip('0')
                    
                    text_param = quote_plus(new_body or "")
                    click_url = f"https://api.whatsapp.com/send?phone={phone_param}&text={text_param}"

                    outgoing.status = 'pending'
                    outgoing.save(update_fields=['status'])
                    return Response({
                        "message":"Click URL generated. Open to send in WhatsApp.",
                        "click_url": click_url,
                        "id": str(outgoing.id)
                    }, status=201)
                except Exception:
                    logging.exception("WhatsApp click-url generation failed")
                    outgoing.status = 'failed'
                    outgoing.save(update_fields=['status'])
                    return Response({"error":"Failed to prepare WhatsApp send."}, status=500)

            # SMS
            if channel == "sms":
                sent_ok = _send_sms(recipient, new_body)
                if sent_ok:
                    outgoing.status = 'sent'
                    outgoing.sent_at = timezone.now()
                    outgoing.save(update_fields=['status','sent_at'])
                    return Response({"message":"Sent successfully.", "id": str(outgoing.id)}, status=201)
                outgoing.status = 'failed'
                outgoing.save(update_fields=['status'])
                return Response({"error":"Failed to send."}, status=500)
            
            return Response({"error":"Invalid channel."}, status=400)