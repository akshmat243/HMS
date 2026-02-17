from django.core.exceptions import ValidationError
from .models import InventoryItem


def consume_inventory(item: InventoryItem, quantity: float):
    if item.stock_level < quantity:
        raise ValidationError(
            f"{item.name} stock insufficient. Available: {item.stock_level}"
        )

    item.stock_level -= quantity
    item.save()
