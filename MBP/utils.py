from django.apps import apps
from .models import AppModel, AuditLog
from django.utils.text import slugify

def populate_app_models():
    for model in apps.get_models():
        model_name = model.__name__
        app_label = model._meta.app_label
        verbose_name = model._meta.verbose_name.title()

        if not AppModel.objects.filter(name=model_name, app_label=app_label).exists():
            AppModel.objects.create(
                name=model_name,
                slug=slugify(model_name),
                verbose_name=verbose_name,
                app_label=app_label,
                description=f"Auto-added model: {verbose_name}"
            )


# python manage.py shell

# from MBP.utils import populate_app_models
# populate_app_models()

import json
import uuid
import datetime
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.fields.files import FileField, ImageField
from django.db.models import Model

def serialize_instance(instance):
    data = {}
    for field in instance._meta.fields:
        field_name = field.name
        value = getattr(instance, field_name, None)

        if isinstance(field, (FileField, ImageField)):
            data[field_name] = value.url if value else None

        elif isinstance(value, (uuid.UUID, datetime.datetime, datetime.date)):
            data[field_name] = str(value)

        elif isinstance(value, Model):
            data[field_name] = str(value)

        else:
            try:
                json.dumps(value, cls=DjangoJSONEncoder)
                data[field_name] = value
            except (TypeError, ValueError):
                data[field_name] = str(value)

    return data


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')

def get_user_agent(request):
    return request.META.get('HTTP_USER_AGENT', '')

def log_audit(request, action, model_name=None, object_id=None, details=None, old_data=None, new_data=None):
    print(f"3.1 ✅ Calling log_audit_from_user for {model_name}, action: {action}")
    try:
        AuditLog.objects.create(
            user=request.user if request and request.user.is_authenticated else None,
            action=action,
            model_name=model_name,
            object_id=str(object_id) if object_id else None,
            details=details,
            old_data=old_data,
            new_data=new_data,
            ip_address=get_client_ip(request) if request else None,
            user_agent=get_user_agent(request) if request else None
        )
    except Exception as e:
        print("❌ Failed to create audit log:", e)

def log_audit_from_user(user, action, model_name=None, object_id=None, details=None, old_data=None, new_data=None):
    print(f"3.2 ✅ Calling log_audit_from_user for {model_name}, action: {action}")
    try:
        AuditLog.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=str(object_id) if object_id else None,
            details=details,
            old_data=old_data,
            new_data=new_data
        )
    except Exception as e:
        print("❌ Failed to create audit log:", e)
