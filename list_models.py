from google import genai

from config import GEMINI_API_KEY

# Words that mark models that make pictures or sound, or do other jobs.
# We need a model that READS a picture and answers in text.
SKIP = ("image", "tts", "audio", "live", "native", "embed", "robotics", "computer-use", "imagen", "veo")

client = genai.Client(api_key=GEMINI_API_KEY)
print("Models that can read a prescription picture and answer in text:")
for model in client.models.list():
    name = model.name.replace("models/", "")
    if "generateContent" not in (model.supported_actions or []):
        continue
    if "flash" not in name:
        continue
    if any(word in name for word in SKIP):
        continue
    print(" ", name)