from django.db import transaction
from .models import CampaignExpense

@transaction.atomic
def add_campaign_expense(campaign, amount, **kwargs):
    if campaign.total_spent + amount > campaign.budget:
        raise ValueError(
            f"Budget exceeded. Remaining: {campaign.remaining_budget}"
        )

    expense = CampaignExpense.objects.create(
        campaign=campaign,
        amount=amount,
        **kwargs
    )

    return expense