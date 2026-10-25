import sys
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from config import GEMINI_API_KEY, GEMINI_MODEL

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
}
MAX_BYTES = 10 * 1024 * 1024

PROMPT = """You are reading a photo of a medical prescription.
Copy ONLY what is written on the paper. Never add, correct, expand or guess anything.

Rules:
- Do not write generic or salt names unless they are written on the paper.
- Do not write any dose, strength or duration that is not written on the paper.
- For each medicine, written_text is the exact words of that line, as written.
- name, strength, dose, frequency and duration are copied exactly as written
  (for example "1 OD 9 AM" or "x 1 mth"). Use null for anything that is not written.
- If any part of a medicine line is hard to read, set unclear to true and use null
  for the part you cannot read. Do not guess.
- Copy the date exactly as written. If it could be read two ways, copy it as written and do not choose.
- Ignore the patient's name, age, vitals and complaints. Do not return them.
- If there are no medicines, return an empty list."""


# What the AI must return. No default values here, on purpose, so that
# Gemini always has to fill in every field (null when nothing is written).
class ReadMedicine(BaseModel):
    written_text: str
    name: str
    strength: Optional[str]
    dose: Optional[str]
    frequency: Optional[str]
    duration: Optional[str]
    unclear: bool


class PrescriptionRead(BaseModel):
    prescription_date: Optional[str]
    doctor_name: Optional[str]
    medicines: list[ReadMedicine]


def read_prescription(image_path, client=None) -> PrescriptionRead:
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"File not found: {path}")
    mime_type = MIME_TYPES.get(path.suffix.lower())
    if mime_type is None:
        raise ValueError("Use a JPG, PNG or PDF file")
    data = path.read_bytes()


    print(f"Image size: {len(data) / (1024 * 1024):.2f} MB")


    if len(data) > MAX_BYTES:
        raise ValueError("File is larger than 10 MB")

    if client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("No key found. Check the .env file.")
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=120_000),
        )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_bytes(data=data, mime_type=mime_type), PROMPT],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=PrescriptionRead,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini sent back nothing. Try again, or try a clearer photo.")
    return PrescriptionRead.model_validate_json(response.text)


def show(result: PrescriptionRead) -> None:
    print("Date (as written):", result.prescription_date or "-")
    print("Doctor:", result.doctor_name or "-")
    print()
    if not result.medicines:
        print("No medicines found.")
        return
    for number, med in enumerate(result.medicines, start=1):
        flag = "   <-- UNCLEAR, ask the person" if med.unclear else ""
        print(f"{number}. {med.name}{flag}")
        print(f"   written as : {med.written_text}")
        print(f"   strength   : {med.strength or '-'}")
        print(f"   dose       : {med.dose or '-'}")
        print(f"   frequency  : {med.frequency or '-'}")
        print(f"   duration   : {med.duration or '-'}")
        print()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python reader.py samples\\your-photo.jpg")
    try:
        result = read_prescription(sys.argv[1])
    except Exception as error:
        raise SystemExit(f"Could not read the prescription: {error}")
    show(result)


if __name__ == "__main__":
    main()