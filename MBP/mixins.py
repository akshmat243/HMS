from django.db.models import Q


class ModuleScopeMixin:
    """
    Applies hotel / restaurant module-based filtering automatically.
    Works with ProtectedModelViewSet.
    """

    module_field_map = {
        "hotel": "assignments__hotel__isnull",
        "restaurant": "assignments__restaurant__isnull",
    }

    def apply_module_scope(self, queryset):
        user = self.request.user

        # Superuser → no restriction
        if user.is_superuser:
            return queryset

        # Users without role → no access
        role = getattr(user, "role", None)
        if not role:
            return queryset.none()

        role_name = role.name.lower()

        # Staff → only self
        if role_name == "staff":
            return queryset.filter(user=user)

        # Admin → module-based filtering
        if role_name == "admin":
            modules = set(
                user.usermodule_set.values_list("module", flat=True)
            )

            if not modules:
                return queryset.none()

            q = None
            for module in modules:
                field = self.module_field_map.get(module)
                if field:
                    condition = {field: False}
                    q = q | Q(**condition) if q else Q(**condition)

            return queryset.filter(q, assignments__is_active=True).distinct()

        return queryset.none()
