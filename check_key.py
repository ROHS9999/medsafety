from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL

if not GEMINI_API_KEY:
    raise SystemExit("No key found. Check that the .env file is in this folder.")

print("Key found:", len(GEMINI_API_KEY), "characters. Model:", GEMINI_MODEL)

client = genai.Client(api_key=GEMINI_API_KEY)
reply = client.models.generate_content(
    model=GEMINI_MODEL,
    contents="Reply with the single word: OK",
)
print("Gemini replied:", reply.text.strip())