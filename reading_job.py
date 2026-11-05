from google.genai import errors
from pydantic import ValidationError

import models
from checker import check_prescription
from database import SessionLocal
from reader import read_prescription

MAX_MEDICINES = 30

# The tests replace this with a pretend reader, so no test calls Google.
read_with_ai = read_prescription


def clip(text, limit):
    """Cut very long text, so one bad answer cannot fill the database."""
    return text[:limit] if text else text


def friendly_error(error: Exception) -> str:
    """A short message that is safe to show. It never shows file paths or Google's raw reply."""
    if isinstance(error, errors.APIError):
        if error.code == 429:
            return "Google's free reading limit was reached. Try again later."
        if error.code in (500, 503, 504):
            return "Google was too busy to read this. Try again in a few minutes."
        return "Google could not read this file."
    if isinstance(error, ValidationError):
        return "The reading came back in a wrong shape. Try again."
    if isinstance(error, ValueError):
        return "This file cannot be read. Use a JPG, PNG or PDF under 10 MB."
    return "The prescription could not be read. Try again."


def save_reading(db, prescription, checked):
    # Remove an earlier reading that nobody confirmed yet.
    # Medicines the person typed or confirmed are never touched.
    db.query(models.Medicine).filter(
        models.Medicine.prescription_id == prescription.id,
        models.Medicine.confirmed.is_(False),
    ).delete()

    for med in checked.medicines[:MAX_MEDICINES]:
        db.add(
            models.Medicine(
                user_id=prescription.user_id,
                prescription_id=prescription.id,
                name=clip(med.name, 200) or "(unreadable)",
                strength=clip(med.strength, 200),
                dose=clip(med.dose, 200),
                frequency=clip(med.frequency, 200),
                duration_text=clip(med.duration, 200),
                written_text=clip(med.written_text, 500),
                unclear=med.unclear,
                problems_text=clip("\n".join(med.problems), 1000) or None,
                confirmed=False,
            )
        )

    prescription.date_as_written = clip(checked.prescription_date, 100)
    prescription.doctor_as_written = clip(checked.doctor_name, 200)
    prescription.reading_status = "ready"
    prescription.reading_error = None
    prescription.list_confirmed = False
    prescription.reading_note = clip(" ".join(checked.warnings), 500) or None
    db.commit()


def read_in_background(prescription_id: int):
    """Runs after the upload has already been answered. Reading can take a minute or more."""
    db = SessionLocal()
    try:
        prescription = db.get(models.Prescription, prescription_id)
        if prescription is None or not prescription.file_path:
            return
        try:
            checked = check_prescription(read_with_ai(prescription.file_path))
            save_reading(db, prescription, checked)
        except Exception as error:
            print(f"[reading] prescription {prescription_id} failed: {error!r}")
            db.rollback()
            prescription = db.get(models.Prescription, prescription_id)
            prescription.reading_status = "failed"
            prescription.reading_error = friendly_error(error)
            db.commit()
    finally:
        db.close()


def schedule_reading(background_tasks, prescription_id: int):
    background_tasks.add_task(read_in_background, prescription_id)
