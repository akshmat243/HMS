import google.generativeai as genai
from django.conf import settings

# Configure Gemini with your API key
genai.configure(api_key=settings.GEMINI_API_KEY)

def generate_text(prompt: str) -> str:
    """
    Generates short text from Gemini AI based on the prompt.
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")  # lightweight & fast
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error: {str(e)}"




# def has_module(user, module):
#     if not user or not user.is_authenticated:
#         return False

#     return user.modules.filter(
#         module=module,
#         is_active=True
#     ).exists()


# def has_hotel_module(user):
#     return has_module(user, "hotel")


# def has_restaurant_module(user):
#     return has_module(user, "restaurant")
# class ProtectedModelViewSet(ModelViewSet):
#     module_required = None  # "hotel" / "restaurant" / None

#     def get_queryset(self):
#         qs = super().get_queryset()
#         user = self.request.user

#         # 🔒 Module-level restriction
#         if self.module_required:
#             if not has_module(user, self.module_required):
#                 return qs.none()

#         return qs


