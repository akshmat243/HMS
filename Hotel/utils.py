from django.core.exceptions import ValidationError
from accounts.models import UserModule

def ensure_module(user, module):
    """
    Ensure user has a module.
    Raise error if already exists.
    """
    if UserModule.objects.filter(user=user, module=module).exists():
        raise ValidationError(
            f"{module.capitalize()} module already exists for this admin."
        )

    return UserModule.objects.create(
        user=user,
        module=module,
        is_active=True
    )
