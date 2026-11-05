import math
import re
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from knowledge import Knowledge, default_knowledge

SEVERITY_RANK = {"Major": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}
LEVEL_RANK = {"Avoid": 0, "Caution": 1}
ALLERGY_RANK = {"severe": 0, "moderate": 1, "mild": 2, None: 3}
MAX_WASHOUT_DAYS = 365

SOURCE = "DDInter"
NOT_A_GUARANTEE = (
    "No warning does not mean the medicines are safe. This check only uses the DDInter data, "
    "a small starter set of rules, and the information saved here. "
    "Confirm with a doctor or pharmacist."
)

# The same medicine has different names in India/UK and in America.
# For each name, other spellings to try. The data friend should add more.
ALIASES = {
    "paracetamol": ["acetaminophen"], "acetaminophen": ["paracetamol"],
    "aspirin": ["acetylsalicylic acid"], "acetylsalicylic acid": ["aspirin"],
    "salbutamol": ["albuterol"], "albuterol": ["salbutamol"],
    "adrenaline": ["epinephrine"], "epinephrine": ["adrenaline"],
    "noradrenaline": ["norepinephrine"], "norepinephrine": ["noradrenaline"],
    "frusemide": ["furosemide"], "glibenclamide": ["glyburide"],
    "lignocaine": ["lidocaine"], "pethidine": ["meperidine"],
    "rifampicin": ["rifampin"], "rifampin": ["rifampicin"],
    "thyroxine": ["levothyroxine"], "l-thyroxine": ["levothyroxine"],
    "amoxycillin": ["amoxicillin"], "clavulanate": ["clavulanic acid"],
    "vitamin d3": ["cholecalciferol"], "vitamin d": ["cholecalciferol"],
    "vitamin c": ["ascorbic acid"], "vitamin b12": ["cyanocobalamin"],
}

# Words that name the form of a salt, not the medicine itself: 'metformin hydrochloride'.
SALT_WORDS = {
    "hydrochloride", "hcl", "dihydrochloride", "sodium", "potassium", "sulfate", "sulphate", "maleate",
    "besylate", "besilate", "tartrate", "mesylate", "citrate", "phosphate", "succinate", "acetate",
    "fumarate", "hydrobromide", "bromide", "dihydrate", "monohydrate", "trihydrate", "anhydrous",
}

STRENGTH = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|%)\b", re.IGNORECASE)


# ---------------------------------------------------------------- names
def clean(name: str) -> str:
    name = STRENGTH.sub(" ", name.lower())
    return re.sub(r"\s+", " ", name).strip(" .,;:-")


def split_salts(salt_name: str) -> list:
    """'Ibuprofen + Paracetamol' -> ['ibuprofen', 'paracetamol']"""
    parts = re.split(r"\s*(?:\+|/|&|,|;)\s*|\s+and\s+", salt_name)
    return [clean(part) for part in parts if clean(part)]


def spellings_to_try(name: str):
    base = clean(name)
    yield base
    yield from ALIASES.get(base, [])
    no_brackets = clean(re.sub(r"\(.*?\)", " ", base))
    if no_brackets and no_brackets != base:
        yield no_brackets
        yield from ALIASES.get(no_brackets, [])
    stripped = " ".join(word for word in no_brackets.split() if word not in SALT_WORDS)
    if stripped and stripped != no_brackets:
        yield stripped
        yield from ALIASES.get(stripped, [])


def spellings(name: str) -> set:
    return {spelling for spelling in spellings_to_try(name) if spelling}


def resolve(name: str, known: set) -> Optional[str]:
    """The name as it is spelled in the interaction data, or None if it is not there."""
    return next((spelling for spelling in spellings_to_try(name) if spelling in known), None)


def alias_in_text(alias: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text.lower()) is not None


# ---------------------------------------------------------------- what the check returns
class SaltIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    salt_name: Optional[str] = Field(default=None, max_length=200)


class CheckedItem(BaseModel):
    medicine_id: int
    name: str
    salts: list[str]


class NotChecked(BaseModel):
    medicine_id: int
    name: str
    reason: str


class DuplicateWarning(BaseModel):
    salt: str
    medicines: list[str]
    message: str


class InteractionWarning(BaseModel):
    severity: str
    medicine_a: str
    medicine_b: str
    salt_a: str
    salt_b: str
    message: str
    timing: Optional[str] = None
    source: str


class AllergyWarning(BaseModel):
    medicine: str
    salt: str
    allergy: str
    allergy_severity: Optional[str] = None
    match: str                      # 'same drug' or 'same family'
    family: Optional[str] = None
    message: str


class IllnessWarning(BaseModel):
    level: str                      # Avoid or Caution
    medicine: str
    salt: str
    illness: str
    because_of: str
    message: str
    source: str


class SafetyReport(BaseModel):
    checked: list[CheckedItem]
    not_checked: list[NotChecked]
    allergy_warnings: list[AllergyWarning]
    illness_warnings: list[IllnessWarning]
    duplicates: list[DuplicateWarning]
    interactions: list[InteractionWarning]       # rated: Major, Moderate or Minor, and overlapping in time
    unrated: list[InteractionWarning]            # listed in DDInter, but no severity given
    separated: list[InteractionWarning]          # listed, but the medicines do not overlap in time
    still_in_body: list[str]                     # finished courses that may still be active
    conditions_counted: list[str]
    conditions_ignored: list[str]
    notes: list[str]


# ---------------------------------------------------------------- reading the data
def current_confirmed(db: Session, user_id: int) -> list:
    """Confirmed medicines that are not finished yet."""
    return (
        db.query(models.Medicine)
        .filter(
            models.Medicine.user_id == user_id,
            models.Medicine.confirmed.is_(True),
            or_(models.Medicine.end_date.is_(None), models.Medicine.end_date >= date.today()),
        )
        .order_by(models.Medicine.id)
        .all()
    )


def known_names(db: Session) -> set:
    first = {row[0] for row in db.query(models.DrugInteraction.drug_a).distinct()}
    second = {row[0] for row in db.query(models.DrugInteraction.drug_b).distinct()}
    return first | second


def lookup_level(db: Session, name_a: str, name_b: str) -> Optional[str]:
    drug_a, drug_b = sorted((name_a, name_b))
    row = (
        db.query(models.DrugInteraction.level)
        .filter(models.DrugInteraction.drug_a == drug_a, models.DrugInteraction.drug_b == drug_b)
        .first()
    )
    return row[0] if row else None


def half_life_lookup(knowledge: Knowledge) -> dict:
    lookup = {}
    for name, entry in knowledge.half_lives.items():
        for spelling in spellings(name):
            lookup.setdefault(spelling, entry)
    return lookup


def washout_for(medicine, components: list, lookup: dict):
    """(days the medicine may stay active after the last dose, was the half-life known?)
    Rule of thumb: about 5 half-lives. Some medicines have a known longer effect."""
    if medicine.half_life_hours:
        return min(math.ceil(5 * medicine.half_life_hours / 24), MAX_WASHOUT_DAYS), True
    days, known = 0, False
    for component in components:
        entry = next((lookup[s] for s in spellings(component) if s in lookup), None)
        if entry is None:
            continue
        if entry["override_days"] is not None:
            entry_days = entry["override_days"]
        else:
            entry_days = math.ceil(5 * entry["hours"] / 24)
        days, known = max(days, entry_days), True
    return min(days, MAX_WASHOUT_DAYS), known


def active_entries(db: Session, user_id: int, today: date, knowledge: Knowledge) -> list:
    """Confirmed medicines that are being taken, or finished but may still be active in the body."""
    lookup = half_life_lookup(knowledge)
    rows = (
        db.query(models.Medicine)
        .filter(
            models.Medicine.user_id == user_id,
            models.Medicine.confirmed.is_(True),
            or_(models.Medicine.end_date.is_(None),
                models.Medicine.end_date >= today - timedelta(days=MAX_WASHOUT_DAYS)),
        )
        .order_by(models.Medicine.id)
        .all()
    )
    entries = []
    for medicine in rows:
        components = split_salts(medicine.salt_name or "")
        days, known = washout_for(medicine, components, lookup)
        until = medicine.end_date + timedelta(days=days) if medicine.end_date else None
        if until is not None and until < today:
            continue
        entries.append(SimpleNamespace(
            medicine=medicine, components=components, washout_days=days, washout_known=known,
            start=medicine.start_date or today, end=medicine.end_date, until=until,
            finished=bool(medicine.end_date and medicine.end_date < today)))
    return entries


def egfr_of(db: Session, user_id: int):
    """The newest kidney value: from a test result if there is one, else from the profile."""
    lab = (
        db.query(models.LabResult)
        .filter(models.LabResult.user_id == user_id)
        .order_by(models.LabResult.taken_on.desc(), models.LabResult.id.desc())
        .all()
    )
    lab = next((row for row in lab if row.test_name.strip().lower() in ("egfr", "e-gfr", "gfr", "estimated gfr")), None)
    if lab is not None:
        return lab.value, f"test result of {lab.taken_on}"
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    if profile is not None and profile.kidney_egfr is not None:
        return profile.kidney_egfr, "profile"
    return None, None


def load_person(db: Session, user_id: int):
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    egfr, egfr_source = egfr_of(db, user_id)
    return SimpleNamespace(
        allergies=db.query(models.Allergy).filter(models.Allergy.user_id == user_id).order_by(models.Allergy.id).all(),
        conditions=db.query(models.Condition).filter(models.Condition.user_id == user_id).order_by(models.Condition.id).all(),
        egfr=egfr, egfr_source=egfr_source,
        pregnant=bool(profile and profile.is_pregnant),
    )


# ---------------------------------------------------------------- the checks
def overlap(a, b) -> bool:
    """Are the two medicines active at the same time? (until = last day, plus the washout)"""
    return (a.until is None or b.start <= a.until) and (b.until is None or a.start <= b.until)


def interaction_message(severity, medicine_a, medicine_b, salt_a, salt_b) -> str:
    if severity == "Unknown":
        return (f"{medicine_a} ({salt_a}) and {medicine_b} ({salt_b}) are listed as interacting, "
                "but how serious it is has not been rated. Ask a doctor or pharmacist.")
    return (f"{severity.upper()}: {medicine_a} ({salt_a}) and {medicine_b} ({salt_b}) may interact. "
            "Ask a doctor or pharmacist before taking them together.")


def family_forms(family: dict) -> set:
    forms = set()
    for name in family["aliases"] + family["members"] + [family["name"]]:
        forms |= spellings(name)
    return forms


def check_allergies(items: list, allergies: list, knowledge: Knowledge) -> list:
    best = {}                                    # (medicine id, allergy id) -> warning
    for allergy in allergies:
        allergy_forms = spellings(allergy.substance)
        if not allergy_forms:
            continue
        families = [f for f in knowledge.allergy_families if allergy_forms & family_forms(f)]
        for medicine, components in items:
            for component in components:
                forms = spellings(component)
                if forms & allergy_forms:
                    warning = AllergyWarning(
                        medicine=medicine.name, salt=component, allergy=allergy.substance,
                        allergy_severity=allergy.severity, match="same drug",
                        message=(f"You listed an allergy to {allergy.substance}. {medicine.name} contains {component}. "
                                 "Do not take it without asking a doctor or pharmacist."))
                else:
                    family = next((f for f in families if forms & family_forms(f)), None)
                    if family is None:
                        continue
                    extra = f" {family['note']}" if family["note"] else ""
                    warning = AllergyWarning(
                        medicine=medicine.name, salt=component, allergy=allergy.substance,
                        allergy_severity=allergy.severity, match="same family", family=family["name"],
                        message=(f"You listed an allergy to {allergy.substance}. {medicine.name} contains {component}, "
                                 f"which is in the same group ({family['name']}). It can cause a similar reaction. "
                                 f"Ask a doctor or pharmacist before taking it.{extra}"))
                key = (medicine.id, allergy.id)
                if key not in best or (warning.match == "same drug" and best[key].match != "same drug"):
                    best[key] = warning
    return sorted(best.values(), key=lambda w: (w.match != "same drug", ALLERGY_RANK.get(w.allergy_severity, 3), w.medicine))


def split_conditions(conditions: list):
    """Short-term illnesses that are over are not counted. Long-term ones always are."""
    counted, ignored = [], []
    for condition in conditions:
        if condition.status == "ongoing":
            counted.append(condition)
        elif condition.acuity_type == "chronic":
            counted.append(condition)
        else:
            ignored.append(condition)
    return counted, ignored


def describe_condition(condition, counted: bool) -> str:
    base = f"{condition.name} ({condition.acuity_type}, {condition.status})"
    if counted and condition.status != "ongoing":
        return base + " - counted, because long-term illnesses do not simply expire"
    return base if counted else base + " - not counted, it is over"


def check_illnesses(items, counted, person, knowledge):
    triggers = [(c.name, c.name) for c in counted]                      # (what to show, text to match)
    if person.pregnant:
        triggers.append(("pregnancy (from the profile)", "pregnancy"))

    best, matched_texts = {}, set()
    for rule in knowledge.illness_rules:
        reasons = []
        for shown, text in triggers:
            if any(alias_in_text(alias, text) for alias in rule["aliases"]):
                reasons.append(shown)
                matched_texts.add(shown)
        if rule["egfr_below"] is not None and person.egfr is not None and person.egfr < rule["egfr_below"]:
            reasons.append(f"kidney value eGFR {person.egfr:g} ({person.egfr_source}) is below {rule['egfr_below']:g}")
        if not reasons:
            continue
        drug_forms = set()
        for drug in rule["drugs"]:
            drug_forms |= spellings(drug)
        for medicine, components in items:
            for component in components:
                if not (spellings(component) & drug_forms):
                    continue
                warning = IllnessWarning(
                    level=rule["level"], medicine=medicine.name, salt=component, illness=rule["illness"],
                    because_of=reasons[0], source=rule["source"],
                    message=(f"{rule['level'].upper()}: {medicine.name} contains {component}. "
                             f"{rule['why']} (Because of: {reasons[0]}.)"))
                key = (medicine.id, component, rule["illness"])
                if key not in best or LEVEL_RANK[warning.level] < LEVEL_RANK[best[key].level]:
                    best[key] = warning
    unmatched = [shown for shown, _ in triggers if shown not in matched_texts]
    ordered = sorted(best.values(), key=lambda w: (LEVEL_RANK[w.level], w.medicine, w.illness))
    return ordered, unmatched


def run_safety_check(db: Session, entries: list, person, knowledge: Knowledge, today: date) -> SafetyReport:
    known = known_names(db)
    notes = []
    if not known:
        notes.append("The interaction data has not been loaded yet. Run load_interactions.py.")

    checked, not_checked, usable, unknown_parts = [], [], [], []
    for index, entry in enumerate(entries):
        entry.index = index
        medicine = entry.medicine
        if not entry.components:
            not_checked.append(NotChecked(
                medicine_id=medicine.id, name=medicine.name,
                reason="No salt name is saved for this medicine yet, so it was not checked."))
            continue
        parts = [(resolve(c, known) or c, resolve(c, known), c) for c in entry.components]   # (merged name, name in data, as typed)
        usable.append((entry, parts))
        in_data = [typed for _, data_name, typed in parts if data_name]
        if not in_data:
            not_checked.append(NotChecked(
                medicine_id=medicine.id, name=medicine.name,
                reason=(f"'{medicine.salt_name}' is not in the interaction data, so no medicine-with-medicine "
                        "check was done for it. Allergy and illness checks still ran.")))
        else:
            checked.append(CheckedItem(medicine_id=medicine.id, name=medicine.name, salts=in_data))
            for _, data_name, typed in parts:
                if not data_name:
                    unknown_parts.append(f"'{typed}' (in {medicine.name})")

    items = [(entry.medicine, [typed for _, _, typed in parts]) for entry, parts in usable]

    # allergies
    allergy_warnings = check_allergies(items, person.allergies, knowledge)

    # illnesses: short-term illnesses that are over are ignored
    counted, ignored = split_conditions(person.conditions)
    illness_warnings, unmatched = check_illnesses(items, counted, person, knowledge)

    # same ingredient in two medicines that are active at the same time
    owners, shown_as = {}, {}
    for entry, parts in usable:
        for used, _, typed in parts:
            shown_as.setdefault(used, typed)
            group = owners.setdefault(used, [])
            if all(entry is not other for other in group):
                group.append(entry)
    duplicates = []
    for salt, group in owners.items():
        involved = []
        for i, first in enumerate(group):
            for second in group[i + 1:]:
                if overlap(first, second):
                    for entry in (first, second):
                        if all(entry is not other for other in involved):
                            involved.append(entry)
        if len(involved) > 1:
            names = [entry.medicine.name for entry in involved]
            duplicates.append(DuplicateWarning(
                salt=shown_as[salt], medicines=names,
                message=f"{' and '.join(names)} both contain {shown_as[salt]}. Taking both may mean too much of it."))

    # medicine with medicine, and do they overlap in time?
    overlapping, separated, seen = [], [], set()
    for position, (entry_a, parts_a) in enumerate(usable):
        for entry_b, parts_b in usable[position + 1:]:
            for _, name_a, typed_a in parts_a:
                for _, name_b, typed_b in parts_b:
                    if not name_a or not name_b or name_a == name_b:
                        continue
                    key = (entry_a.index, entry_b.index, *sorted((name_a, name_b)))
                    if key in seen:
                        continue
                    seen.add(key)
                    level = lookup_level(db, name_a, name_b)
                    if not level:
                        continue
                    a, b = entry_a.medicine.name, entry_b.medicine.name
                    warning = InteractionWarning(
                        severity=level, medicine_a=a, medicine_b=b, salt_a=typed_a, salt_b=typed_b,
                        source=SOURCE, message=interaction_message(level, a, b, typed_a, typed_b))
                    if overlap(entry_a, entry_b):
                        together_from = max(entry_a.start, entry_b.start)
                        ends = [e for e in (entry_a.until, entry_b.until) if e is not None]
                        warning.timing = (f"Both would be active together from {together_from}"
                                          + (f" until about {min(ends)}." if ends else " (no end date yet)."))
                        overlapping.append(warning)
                    else:
                        first, second = (entry_a, entry_b) if entry_b.start > entry_a.until else (entry_b, entry_a)
                        warning.timing = (f"{second.medicine.name} starts on {second.start}, after "
                                          f"{first.medicine.name} should have cleared the body (about {first.until}). "
                                          "Their schedules do not overlap, so this interaction should not apply as planned.")
                        separated.append(warning)
    order = lambda w: (SEVERITY_RANK.get(w.severity, 3), w.medicine_a, w.medicine_b)
    overlapping.sort(key=order)
    separated.sort(key=order)
    interactions = [w for w in overlapping if w.severity != "Unknown"]
    unrated = [w for w in overlapping if w.severity == "Unknown"]

    still_in_body = [
        f"{e.medicine.name}: the course ended on {e.end}, but it may still be active until about {e.until}."
        for e in entries if e.finished]

    assumed = [e.medicine.name for e in entries if e.end and e.components and not e.washout_known]

    if allergy_warnings:
        notes.append(f"{len(allergy_warnings)} allergy warning(s) found.")
    if unrated:
        notes.append(f"{len(unrated)} more interaction(s) are listed without a severity rating. See 'unrated'.")
    if separated:
        notes.append(f"{len(separated)} interaction(s) are listed, but the medicines do not overlap in time. See 'separated'.")
    if not_checked:
        notes.append(f"{len(not_checked)} medicine(s) could not be fully checked.")
    if unknown_parts:
        notes.append("Not found in the interaction data, so not checked for interactions: " + ", ".join(unknown_parts) + ".")
    if assumed:
        notes.append("We do not know how long these stay in the body, so we assumed they left on the last day: "
                     + ", ".join(assumed) + ".")
    if unmatched:
        notes.append("No rules exist yet for: " + ", ".join(unmatched) + ". These were not checked against the medicines.")
    notes.append(NOT_A_GUARANTEE)

    return SafetyReport(
        checked=checked, not_checked=not_checked, allergy_warnings=allergy_warnings,
        illness_warnings=illness_warnings, duplicates=duplicates, interactions=interactions,
        unrated=unrated, separated=separated, still_in_body=still_in_body,
        conditions_counted=[describe_condition(c, True) for c in counted],
        conditions_ignored=[describe_condition(c, False) for c in ignored],
        notes=notes)


def check_for_user(db: Session, user_id: int, today: Optional[date] = None, knowledge: Optional[Knowledge] = None):
    knowledge = knowledge or default_knowledge()
    today = today or date.today()
    entries = active_entries(db, user_id, today, knowledge)
    return run_safety_check(db, entries, load_person(db, user_id), knowledge, today)
