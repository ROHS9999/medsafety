import time
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL
from reader import PROMPT, PrescriptionRead

picture = types.Part.from_bytes(
    data=Path("samples/mock_prescription_1.png").read_bytes(), mime_type="image/png"
)
SHORT = "Read this prescription and list the medicine names."

client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=120_000))

TESTS = [
    ("A: text only", ["Reply with the single word: OK"], types.GenerateContentConfig()),
    ("B: picture, plain answer", [picture, SHORT], types.GenerateContentConfig()),
    (
        "C: picture, JSON answer",
        [picture, SHORT],
        types.GenerateContentConfig(response_mime_type="application/json"),
    ),
    (
        "D: picture, JSON in our exact shape",
        [picture, SHORT],
        types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=PrescriptionRead
        ),
    ),
    (
        "E: the real reader call (long rules, temperature 0)",
        [picture, PROMPT],
        types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=PrescriptionRead,
        ),
    ),
]

print("Model:", GEMINI_MODEL)
for name, contents, config in TESTS:
    started = time.time()
    try:
        reply = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
        seconds = time.time() - started
        print(f"{name}: OK in {seconds:.1f}s -> {(reply.text or '').strip()[:70]!r}")
    except Exception as error:
        seconds = time.time() - started
        print(f"{name}: FAILED after {seconds:.1f}s -> {str(error)[:110]}")
