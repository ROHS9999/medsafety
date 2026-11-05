import re
from typing import Optional

from pydantic import BaseModel

from reader import PrescriptionRead, ReadMedicine

FIELDS = ("strength", "dose", "frequency", "duration")
UNCLEAR_MARKS = ("[unclear]", "illegible", "?")


class CheckedMedicine(BaseModel):
    written_text: str
    name: str
    strength: Optional[str]
    dose: Optional[str]
    frequency: Optional[str]
    duration: Optional[str]
    unclear: bool
    problems: list[str]


class CheckedPrescription(BaseModel):
    prescription_date: Optional[str]
    doctor_name: Optional[str]
    medicines: list[CheckedMedicine]
    warnings: list[str]


def fix_dashes(text: str) -> str:
    """Make the different dash characters the same, so 1-0-1 matches 1–0–1."""
    for dash in ("\u2013", "\u2014", "\u2010", "\u2011", "\u2212"):
        text = text.replace(dash, "-")
    return text


def is_written(value: str, written_text: str) -> bool:
    """Is this value really in the written line?
    Spaces and capital letters do not matter ('650 mg' matches '650mg').
    But the value must stand on its own: '1' does not match inside '10'."""
    characters = [re.escape(c) for c in fix_dashes(value) if not c.isspace()]
    if not characters:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s*".join(characters) + r"(?![a-z0-9])"
    return re.search(pattern, fix_dashes(written_text), re.IGNORECASE) is not None


def check_medicine(med: ReadMedicine) -> CheckedMedicine:
    problems = []
    written = med.written_text.strip()

    if not written:
        problems.append("No written line was returned for this medicine.")

    name = med.name.strip()
    if written and not is_written(name, written):
        problems.append(f"The name '{name}' is not in the written line.")

    values = {}
    for field in FIELDS:
        value = (getattr(med, field) or "").strip() or None
        if value is not None and not is_written(value, written):
            problems.append(f"The {field} '{value}' is not on the paper, so it was removed.")
            value = None
        values[field] = value

    marked_unclear = any(mark in written.lower() for mark in UNCLEAR_MARKS)

    return CheckedMedicine(
        written_text=written,
        name=name,
        unclear=bool(med.unclear or marked_unclear or problems),
        problems=problems,
        **values,
    )


DATE_PATTERNS = (
    r"(?<!\d)\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*(\d{4}|\d{2})(?!\d)",      # 05/10/2026, 5-10-26
    r"(?<!\d)\d{4}\s*-\s*\d{1,2}\s*-\s*\d{1,2}(?!\d)",                         # 2026-10-05
    r"(?<!\d)\d{1,2}\s*(st|nd|rd|th)?\s*[A-Za-z]{3,9}\.?,?\s*(\d{4}|\d{2})(?!\d)",  # 5 Oct 2026
    r"(?<![A-Za-z])[A-Za-z]{3,9}\.?\s*\d{1,2}(?!\d)\s*(st|nd|rd|th)?,?\s*(\d{4}|\d{2})(?!\d)",  # Oct 5, 2026
)


def date_looks_complete(text: str) -> bool:
    """Does the written date have a day, a month and a year?"""
    return any(re.search(pattern, fix_dashes(text)) for pattern in DATE_PATTERNS)


def check_prescription(result: PrescriptionRead) -> CheckedPrescription:
    medicines = [check_medicine(med) for med in result.medicines]
    warnings = []

    counted = result.medicine_lines_on_page
    if counted is not None and counted != len(medicines):
        warnings.append(
            f"The page seems to list {counted} medicines, but {len(medicines)} were read. "
            "Check the photo for missing medicines."
        )

    date = (result.prescription_date or "").strip()
    if date and not date_looks_complete(date):
        warnings.append(f"The date '{date}' looks incomplete. Check it against the photo.")

    return CheckedPrescription(
        prescription_date=result.prescription_date,
        doctor_name=result.doctor_name,
        medicines=medicines,
        warnings=warnings,
    )


def show_checked(result: CheckedPrescription) -> None:
    print("Date (as written):", result.prescription_date or "-")
    print("Doctor:", result.doctor_name or "-")
    print()
    for number, med in enumerate(result.medicines, start=1):
        flag = "   <-- ASK THE PERSON" if med.unclear else ""
        print(f"{number}. {med.name}{flag}")
        print(f"   written as : {med.written_text}")
        for field in FIELDS:
            print(f"   {field:<10} : {getattr(med, field) or '-'}")
        for problem in med.problems:
            print(f"   PROBLEM    : {problem}")
        print()
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    needs = sum(1 for med in result.medicines if med.unclear)
    print(f"{len(result.medicines)} medicines read, {needs} need the person to check.")
