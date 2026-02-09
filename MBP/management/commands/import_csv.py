import csv
import os, uuid
from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, transaction

CSV_DIR = os.path.join(settings.BASE_DIR, "csv_exports")

class Command(BaseCommand):
    help = "Import CSV data (supports app / model / file level import)"

    def add_arguments(self, parser):
        parser.add_argument("--app", type=str, help="Import all models of an app")
        parser.add_argument("--model", type=str, help="Import a single model: app.Model")
        parser.add_argument("--file", type=str, help="Import a specific CSV file")

    def handle(self, *args, **options):
        if not os.path.exists(CSV_DIR):
            self.stdout.write(self.style.ERROR("CSV directory not found"))
            return

        if options["file"]:
            self.import_by_file(options["file"])
            return

        if options["model"]:
            self.import_by_model(options["model"])
            return

        if options["app"]:
            self.import_by_app(options["app"])
            return

        self.stdout.write(
            self.style.ERROR(
                "Please specify --app OR --model OR --file"
            )
        )

    # -------------------------------
    # IMPORT METHODS
    # -------------------------------

    def import_by_file(self, file_name):
        file_path = os.path.join(CSV_DIR, file_name)

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR("CSV file not found"))
            return

        try:
            app_label, model_name = file_name.replace(".csv", "").split("_", 1)
        except ValueError:
            self.stdout.write(self.style.ERROR("Invalid file name format"))
            return

        self.import_model_csv(app_label, model_name, file_name)

    def import_by_model(self, model_path):
        try:
            app_label, model_name = model_path.split(".")
        except ValueError:
            self.stdout.write(self.style.ERROR("Use format app.Model"))
            return

        file_name = f"{app_label}_{model_name}.csv"
        self.import_model_csv(app_label, model_name, file_name)

    def import_by_app(self, app_label):
        for file_name in os.listdir(CSV_DIR):
            if file_name.startswith(f"{app_label}_") and file_name.endswith(".csv"):
                _, model_name = file_name.replace(".csv", "").split("_", 1)
                self.import_model_csv(app_label, model_name, file_name)

    # -------------------------------
    # CORE IMPORT LOGIC (SAFE)
    # -------------------------------

    @transaction.atomic
    def import_model_csv(self, app_label, model_name, file_name):
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            self.stdout.write(self.style.WARNING(
                f"Model not found: {app_label}.{model_name}"
            ))
            return

        file_path = os.path.join(CSV_DIR, file_name)

        if not os.path.exists(file_path):
            self.stdout.write(self.style.WARNING(
                f"CSV not found for {app_label}.{model_name}"
            ))
            return

        required_fields = [
            field.name
            for field in model._meta.fields
            if not field.null and not field.blank and not field.auto_created
        ]

        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            for index, row in enumerate(reader, start=1):
                clean_data = {}

                for field in model._meta.fields:
                    if field.primary_key or field.auto_created:
                        continue

                    field_name = field.name
                    value = row.get(field_name)

                    # ✅ UUID FIELD HANDLE
                    if field.get_internal_type() == "UUIDField":
                        if value:
                            try:
                                clean_data[field_name] = uuid.UUID(value)
                            except ValueError:
                                # Invalid UUID → skip so Django generates new one
                                continue
                        continue

                    # ✅ ForeignKey handling
                    if field.is_relation:
                        if value:
                            try:
                                clean_data[field_name] = field.related_model.objects.get(id=value)
                            except field.related_model.DoesNotExist:
                                clean_data[field_name] = None
                        continue

                    # Normal field
                    clean_data[field_name] = value or None


                # Required field validation
                if any(not clean_data.get(f) for f in required_fields):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped row {index} in {model_name} (missing required field)"
                        )
                    )
                    continue

                try:
                    model.objects.create(**clean_data)
                except IntegrityError as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Row {index} failed for {model_name}: {e}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(f"Imported: {app_label}.{model_name}")
        )
