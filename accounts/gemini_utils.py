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
