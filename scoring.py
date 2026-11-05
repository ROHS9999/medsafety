import csv

from checker import CheckedPrescription, is_written

SCORED_FIELDS = ("strength", "frequency", "duration")


def load_answers(csv_path):
    """Read the answer sheet. One row per medicine.
    Returns {file name: {"date": text, "medicines": [{name, strength, frequency, duration}]}}."""
    answers = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            file_name = (row.get("file") or "").strip()
            if not file_name:
                continue
            entry = answers.setdefault(file_name, {"date": (row.get("date") or "").strip(), "medicines": []})
            name = (row.get("name") or "").strip()
            if name:
                entry["medicines"].append(
                    {"name": name, **{field: (row.get(field) or "").strip() for field in SCORED_FIELDS}}
                )
    return answers


def field_is_right(expected: str, found_parts: list) -> bool:
    """Is the value the AI gave the same as the answer sheet?
    An empty answer means 'nothing is written', so the AI must give nothing (no invented values)."""
    found = " ".join(part for part in found_parts if part).strip()
    if not expected:
        return not found
    return bool(found) and is_written(expected, found)


def score_prescription(expected: dict, checked: CheckedPrescription) -> dict:
    unused = list(checked.medicines)
    score = {
        "expected": len(expected["medicines"]),
        "found": 0,
        "fields": {field: [0, 0] for field in SCORED_FIELDS},   # [right, total]
        "wrong": [],
        "missed": [],
        "extra": [],
        "flagged": sum(1 for med in checked.medicines if med.unclear),
        "date_ok": True,
        "warnings": list(checked.warnings),
    }

    for answer in expected["medicines"]:
        match = next((m for m in unused if is_written(answer["name"], f"{m.name} {m.written_text}")), None)
        if match is None:
            score["missed"].append(answer["name"])
            for field in SCORED_FIELDS:
                if field != "frequency" or answer["frequency"]:
                    score["fields"][field][1] += 1
            continue
        unused.remove(match)
        score["found"] += 1

        found_parts = {
            "strength": [match.strength],
            "frequency": [match.dose, match.frequency],
            "duration": [match.duration],
        }
        for field in SCORED_FIELDS:
            if field == "frequency" and not answer["frequency"]:
                continue                                   # not on the answer sheet: do not score
            score["fields"][field][1] += 1
            if field_is_right(answer[field], found_parts[field]):
                score["fields"][field][0] += 1
            else:
                got = " ".join(p for p in found_parts[field] if p) or "-"
                score["wrong"].append(f"{answer['name']}: {field} should be '{answer[field] or '-'}', got '{got}'")

    score["extra"] = [m.name for m in unused]

    expected_date = expected["date"]
    found_date = (checked.prescription_date or "").strip()
    score["date_ok"] = (not expected_date) or expected_date == found_date
    if not score["date_ok"]:
        score["wrong"].append(f"date should be '{expected_date}', got '{found_date or '-'}'")
    return score


def add_up(scores: list) -> dict:
    total = {
        "files": len(scores), "expected": 0, "found": 0, "extra": 0, "flagged": 0, "dates_ok": 0,
        "fields": {field: [0, 0] for field in SCORED_FIELDS},
    }
    for score in scores:
        total["expected"] += score["expected"]
        total["found"] += score["found"]
        total["extra"] += len(score["extra"])
        total["flagged"] += score["flagged"]
        total["dates_ok"] += 1 if score["date_ok"] else 0
        for field in SCORED_FIELDS:
            total["fields"][field][0] += score["fields"][field][0]
            total["fields"][field][1] += score["fields"][field][1]
    return total


def percent(right: int, total: int) -> str:
    return f"{100 * right / total:.0f}%" if total else "-"
