from celery import Celery
from celery.schedules import crontab

app = Celery('HMS')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'auto-checkout-and-absent-everyday-8pm': {
        'task': 'attendance.tasks.auto_checkout_and_absent_marking',
        'schedule': crontab(hour=20, minute=0),  # runs daily at 8:00 PM
    },
}
