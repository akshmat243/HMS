from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import AuditLog
from .utils import log_audit_from_user

from django.core.serializers.json import DjangoJSONEncoder
import json
import uuid
import datetime

def serialize_instance(instance):
    data = {}

    for field in instance._meta.fields:
        value = getattr(instance, field.name, None)

        if isinstance(value, (uuid.UUID, datetime.datetime)):
            data[field.name] = str(value)
        else:
            try:
                json.dumps(value, cls=DjangoJSONEncoder)
                data[field.name] = value
            except TypeError:
                data[field.name] = str(value)

    return data


@receiver(pre_save)
def capture_old_data(sender, instance, **kwargs):
    if sender == AuditLog:
        return
    if instance.pk:
        try:
            instance._old_data = serialize_instance(sender.objects.get(pk=instance.pk))
        except sender.DoesNotExist:
            instance._old_data = None

@receiver(post_save)
def log_create_or_update(sender, instance, created, **kwargs):
    if sender == AuditLog:
        return
    print(f"1 🚨 Signal fired for {sender.__name__}, created: {created}")

    user = getattr(instance, '_request_user', None)
    if not user:
        return

    model_name = sender.__name__
    object_id = instance.pk
    new_data = serialize_instance(instance)
    old_data = getattr(instance, '_old_data', None)

    if created:
        log_audit_from_user(
            user=user,
            action='create',
            model_name=model_name,
            object_id=object_id,
            details=f"Signal: Created {model_name}: {instance}",
            new_data=new_data
        )
    else:
        log_audit_from_user(
            user=user,
            action='update',
            model_name=model_name,
            object_id=object_id,
            details=f"Signal: Updated {model_name}: {instance}",
            old_data=old_data,
            new_data=new_data
        )

@receiver(post_delete)
def log_deletion(sender, instance, **kwargs):
    if sender == AuditLog:
        return

    user = getattr(instance, '_request_user', None)
    if not user:
        return

    model_name = sender.__name__
    object_id = instance.pk
    old_data = serialize_instance(instance)

    log_audit_from_user(
        user=user,
        action='delete',
        model_name=model_name,
        object_id=object_id,
        details=f"Signal: Deleted {model_name}: {instance}",
        old_data=old_data
    )
