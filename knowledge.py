"""Reads the three small knowledge tables in the 'knowledge' folder:
    allergy_families.csv   medicines that belong to the same allergy group
    illness_rules.csv      medicines to avoid or be careful with, for each illness
    half_lives.csv         how long each medicine stays in the body
Your data friend can open these in Excel and add rows. Use ; between several values."""
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

FOLDER = Path(__file__).parent / "knowledge"
LEVELS = ("Avoid", "Caution")


@dataclass
class Knowledge:
    allergy_families: list
    illness_rules: list
    half_lives: dict


def split_list(text) -> list:
    return [part.strip().lower() for part in (text or "").split(";") if part.strip()]


def number_or_none(text, file, row_number, column) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{file} row {row_number}: {column} '{text}' is not a number") from None


def read_rows(folder: Path, file: str) -> list:
    with open(folder / file, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_knowledge(folder=None) -> Knowledge:
    folder = Path(folder) if folder else FOLDER

    families = []
    for number, row in enumerate(read_rows(folder, "allergy_families.csv"), start=2):
        name = (row.get("family") or "").strip()
        members = split_list(row.get("members"))
        if not name or not members:
            raise ValueError(f"allergy_families.csv row {number}: needs a family name and members")
        families.append({"name": name.lower(), "aliases": split_list(row.get("aliases")),
                         "members": members, "note": (row.get("note") or "").strip()})

    rules = []
    for number, row in enumerate(read_rows(folder, "illness_rules.csv"), start=2):
        level = (row.get("level") or "").strip().title()
        drugs = split_list(row.get("drugs"))
        if level not in LEVELS:
            raise ValueError(f"illness_rules.csv row {number}: level '{row.get('level')}' must be Avoid or Caution")
        if not drugs or not (row.get("illness") or "").strip():
            raise ValueError(f"illness_rules.csv row {number}: needs an illness and drugs")
        rules.append({
            "illness": row["illness"].strip(), "aliases": split_list(row.get("aliases")), "drugs": drugs,
            "level": level, "egfr_below": number_or_none(row.get("egfr_below"), "illness_rules.csv", number, "egfr_below"),
            "why": (row.get("why") or "").strip(), "source": (row.get("source") or "").strip(),
        })

    half_lives = {}
    for number, row in enumerate(read_rows(folder, "half_lives.csv"), start=2):
        salt = (row.get("salt") or "").strip().lower()
        hours = number_or_none(row.get("half_life_hours"), "half_lives.csv", number, "half_life_hours")
        override = number_or_none(row.get("washout_days_override"), "half_lives.csv", number, "washout_days_override")
        if not salt or (hours is None and override is None):
            raise ValueError(f"half_lives.csv row {number}: needs a salt and a half life or a washout override")
        half_lives[salt] = {"hours": hours, "override_days": int(override) if override is not None else None,
                            "note": (row.get("note") or "").strip()}

    return Knowledge(allergy_families=families, illness_rules=rules, half_lives=half_lives)


@lru_cache(maxsize=1)
def default_knowledge() -> Knowledge:
    return load_knowledge()
