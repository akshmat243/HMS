import csv
import os
from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

EXCLUDED_APPS = [
    "auth",
    "admin",
    "contenttypes",
    "sessions",
    "Restaurant",
    "Review"
]

class Command(BaseCommand):
    help = "Export database models to CSV excluding selected apps"

    def handle(self, *args, **options):
        base_dir = os.path.join(settings.BASE_DIR, "csv_exports")
        os.makedirs(base_dir, exist_ok=True)

        for app_config in apps.get_app_configs():
            if app_config.label in EXCLUDED_APPS:
                continue

            for model in app_config.get_models():
                self.export_model_to_csv(model, base_dir)

        self.stdout.write(self.style.SUCCESS("CSV export completed successfully"))

    def export_model_to_csv(self, model, base_dir):
        
        if not model.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped (no data): {model._meta.app_label}.{model.__name__}"
                )
            )
            return
        
        model_name = model.__name__
        app_label = model._meta.app_label

        file_path = os.path.join(base_dir, f"{app_label}_{model_name}.csv")

        fields = [field.name for field in model._meta.fields]

        with open(file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(fields)

            for obj in model.objects.all():
                row = [getattr(obj, field) for field in fields]
                writer.writerow(row)

        self.stdout.write(f"Exported: {file_path}")
