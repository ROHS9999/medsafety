"""Brick 26: explains the safety report in simple words.

The warnings come from our own checks. The AI is only allowed to REWORD them:
- it sees only the facts of each warning (no name, email, age or ids),
- its text is checked, and any text that adds a medicine, a number or a promise
  of safety is thrown away and replaced by our standard message,
- the seriousness label and the closing advice are added by our code, never by the AI,
- if the AI is off, busy or over its limit, the standard messages are shown."""
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from google import genai
from google.genai import errors, types
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import GEMINI_API_KEY, GEMINI_MODEL
from knowledge import default_knowledge
from safety import SafetyReport, check_for_user, known_names

CLOSING = "Ask a doctor or pharmacist."
MAX_AI_FINDINGS = 25
MAX_TEXT = 500
TIMEOUT_MS = 45_000

PROMPT = """You help a patient understand safety warnings about their medicines.
Each finding below was produced by a checking program. Your only job is to rewrite it in very simple words.

Rules:
- Use ONLY the facts written in the finding. Never add a medicine name, number, dose, risk or reason that is not there.
- Keep the seriousness exactly as given. Do not make it sound safer or scarier.
- Do not tell the person to start, stop or change any medicine. The program adds the advice itself.
- Write 1 to 3 short sentences in plain words that a 12-year-old understands. No medical jargon.
- Return every finding, using the same id.

Findings:
"""

# Text the AI may never write unless the facts already say it.
FORBIDDEN_PHRASES = [
    "stop taking", "start taking", "increase the dose", "decrease the dose", "reduce the dose",
    "double the dose", "is safe", "are safe", "completely safe", "perfectly safe", "safe to take",
    "safe together", "no risk", "nothing to worry", "do not worry", "don't worry", "no need to",
    "http", "www.", 
    "for a few days",
    "for several days",
    "for many days",
]

DANGER_WORDS = ["fatal", "death", "die", "deadly", "life-threatening", "emergency"]
SOFTENING_WORDS = ["minor", "mild", "harmless", "unimportant"]
COMMON_WORDS = {"water", "food", "salt", "sugar", "milk", "oil", "tea", "coffee"}

# in-memory only: lost when the server restarts
_cache: dict = {}
_calls = {"day": None, "count": 0}


# ------------------------------------------------------------ what we return
class ExplainedFinding(BaseModel):
    kind: str
    severity: str
    title: str
    explanation: str
    explained_by_ai: bool
    standard_message: str
    source: Optional[str] = None


class ExplainedReport(BaseModel):
    summary: str
    ai_status: str
    findings: list[ExplainedFinding]
    notes: list[str]


class AiAnswer(BaseModel):
    id: int
    text: str


class AiAnswers(BaseModel):
    findings: list[AiAnswer]


@dataclass
class Finding:
    id: int
    kind: str
    severity: str
    title: str
    facts: str            # what the AI is allowed to know
    standard: str         # our own plain message
    source: Optional[str]
    use_ai: bool
    rank: int


# ------------------------------------------------------------ turning the report into findings
def build_findings(report: SafetyReport) -> list:
    found = []

    def add(rank, kind, severity, title, facts, standard, source=None, use_ai=True):
        found.append(Finding(id=0, kind=kind, severity=severity, title=title, facts=facts,
                             standard=standard, source=source, use_ai=use_ai, rank=rank))

    for w in report.allergy_warnings:
        group = f" Group: {w.family}." if w.family else ""
        add(0 if w.match == "same drug" else 1, "allergy", f"Allergy ({w.match})", f"Allergy: {w.medicine}",
            f"Type: allergy. The person listed an allergy to '{w.allergy}' (seriousness of their allergy: "
            f"{w.allergy_severity or 'not given'}). The medicine '{w.medicine}' contains '{w.salt}'. "
            f"Match: {w.match}.{group}", w.message)

    for w in report.illness_warnings:
        add(2 if w.level == "Avoid" else 6, "illness", w.level, f"{w.level}: {w.medicine} and {w.because_of}",
            f"Type: illness check ({w.level}). The medicine '{w.medicine}' contains '{w.salt}'. "
            f"Reason from our rule table: {w.message}", w.message, source=w.source)

    for w in report.interactions:
        rank = {"Major": 3, "Moderate": 5, "Minor": 7}.get(w.severity, 7)
        add(rank, "interaction", w.severity, f"{w.severity} interaction: {w.medicine_a} + {w.medicine_b}",
            f"Type: medicine interaction. Seriousness: {w.severity}. Medicines: '{w.medicine_a}' ({w.salt_a}) and "
            f"'{w.medicine_b}' ({w.salt_b}). Timing: {w.timing or 'not given'}",
            f"{w.message} {w.timing or ''}".strip(), source=w.source)

    for w in report.duplicates:
        add(4, "duplicate", "Check", f"Same ingredient: {', '.join(w.medicines)}",
            f"Type: same ingredient in more than one medicine. Medicines: {', '.join(w.medicines)}. Ingredient: {w.salt}.",
            w.message)

    for w in report.separated:
        add(8, "timing", "Timing", f"Timing: {w.medicine_a} and {w.medicine_b}",
            f"Type: listed interaction, but the medicines do not overlap in time. Seriousness if taken together: "
            f"{w.severity}. Medicines: '{w.medicine_a}' and '{w.medicine_b}'. Timing: {w.timing}",
            f"{w.message} {w.timing}".strip(), source=w.source)

    for text in report.still_in_body:
        add(9, "timing", "Timing", f"Still active: {text.split(':')[0]}", text, text, use_ai=False)

    for w in report.unrated:
        add(10, "interaction", "Not rated", f"Interaction (not rated): {w.medicine_a} + {w.medicine_b}",
            w.message, w.message, source=w.source, use_ai=False)

    for w in report.not_checked:
        add(11, "not checked", "Not checked", f"Not checked: {w.name}", w.reason, w.reason, use_ai=False)

    found.sort(key=lambda f: f.rank)            # most important first; stable inside a rank
    for number, finding in enumerate(found, start=1):
        finding.id = number
    return found


def build_summary(report: SafetyReport) -> str:
    parts = []
    if report.allergy_warnings:
        parts.append(f"{len(report.allergy_warnings)} allergy warning(s)")
    avoid = sum(1 for w in report.illness_warnings if w.level == "Avoid")
    if avoid:
        parts.append(f"{avoid} medicine(s) to avoid because of an illness or pregnancy")
    if len(report.illness_warnings) - avoid:
        parts.append(f"{len(report.illness_warnings) - avoid} illness caution(s)")
    if report.interactions:
        parts.append(f"{len(report.interactions)} medicine interaction(s)")
    if report.duplicates:
        parts.append(f"{len(report.duplicates)} repeated ingredient(s)")
    text = ("We found " + ", ".join(parts) + ". Please go through them with a doctor or pharmacist."
            if parts else "We did not find any warnings in what we could check.")
    if report.not_checked:
        text += f" {len(report.not_checked)} medicine(s) could not be fully checked."
    return text


# ------------------------------------------------------------ checking what the AI wrote
def drug_pattern(db: Session):
    names = {n for n in known_names(db) if len(n) >= 4 and n not in COMMON_WORDS}
    knowledge = default_knowledge()
    for family in knowledge.allergy_families:
        names.update(family["members"])
    for rule in knowledge.illness_rules:
        names.update(rule["drugs"])
    names = sorted((n for n in names if len(n) >= 4 and n not in COMMON_WORDS), key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"(?<![a-z])(" + "|".join(re.escape(n) for n in names) + r")(?![a-z])")


def problem_with(text: str, finding: Finding, pattern) -> Optional[str]:
    """Why this text cannot be used, or None if it is fine."""
    low, facts = text.lower(), finding.facts.lower()
    if not text.strip():
        return "empty"
    if len(text) > MAX_TEXT:
        return "too long"
    for phrase in FORBIDDEN_PHRASES:
        if phrase in low and phrase not in facts:
            return f"contains '{phrase}'"
    for word in DANGER_WORDS + SOFTENING_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low) and not re.search(rf"\b{re.escape(word)}\b", facts):
            return f"uses the word '{word}', which is not in the facts"
    allowed_numbers = set(re.findall(r"\d+", facts))
    for number in re.findall(r"\d+", low):
        if number not in allowed_numbers:
            return f"mentions the number {number}, which is not in the facts"
    if pattern is not None:
        for match in pattern.finditer(low):
            if not re.search(rf"(?<![a-z]){re.escape(match.group(1))}(?![a-z])", facts):
                return f"mentions '{match.group(1)}', which is not in the facts"
    return None


def finish_text(text: str) -> str:
    """Our closing advice is added by the program, never by the AI."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in sentences if "doctor or pharmacist" not in s.lower()]
    return " ".join(kept).strip() + " " + CLOSING


# ------------------------------------------------------------ asking the AI
def make_client():
    if not GEMINI_API_KEY:
        return None
    return genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def ai_switched_off() -> bool:
    return os.getenv("EXPLAIN_WITH_AI", "1").strip().lower() in ("0", "false", "no", "off")


def daily_limit() -> int:
    try:
        return int(os.getenv("EXPLAIN_DAILY_LIMIT", "50"))
    except ValueError:
        return 50


def reserve_call(today: date) -> bool:
    if _calls["day"] != today:
        _calls["day"], _calls["count"] = today, 0
    if _calls["count"] >= daily_limit():
        return False
    _calls["count"] += 1
    return True


def build_prompt(findings: list) -> str:
    return PROMPT + "\n".join(f"[{f.id}] {f.facts}" for f in findings)


def ask_ai(client, prompt: str) -> AiAnswers:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0, response_mime_type="application/json", response_schema=AiAnswers),
    )
    if not response.text:
        raise RuntimeError("empty answer")
    return AiAnswers.model_validate_json(response.text)


def friendly_status(error: Exception) -> str:
    if isinstance(error, errors.APIError):
        if error.code == 429:
            return "Google's free limit was reached, so the standard messages are shown."
        return "Google was busy, so the standard messages are shown."
    return "The AI answer could not be used, so the standard messages are shown."


def explain_report(db: Session, report: SafetyReport, client=None, today: Optional[date] = None) -> ExplainedReport:
    today = today or date.today()
    findings = build_findings(report)
    wanted = [f for f in findings if f.use_ai][:MAX_AI_FINDINGS]
    texts, status = {}, "ok"

    if not wanted:
        status = "Nothing needed an AI explanation."
    elif ai_switched_off():
        status = "AI explanations are switched off, so the standard messages are shown."
    else:
        key = hashlib.sha256((GEMINI_MODEL + "\n" + build_prompt(wanted)).encode()).hexdigest()
        if key in _cache:
            answers = _cache[key]
        else:
            client = client or make_client()
            answers = None
            if client is None:
                status = "No AI key is set, so the standard messages are shown."
            elif not reserve_call(today):
                status = "The daily limit for AI explanations was reached, so the standard messages are shown."
            else:
                try:
                    answers = ask_ai(client, build_prompt(wanted))
                    if len(_cache) >= 200:
                        _cache.clear()
                    _cache[key] = answers
                except Exception as error:
                    print(f"[explainer] AI call failed: {error!r}")
                    status = friendly_status(error)
        if answers is not None:
            pattern = drug_pattern(db)
            by_id = {a.id: a.text for a in answers.findings}
            for finding in wanted:
                text = by_id.get(finding.id)
                reason = "missing from the AI answer" if text is None else problem_with(text, finding, pattern)
                if reason is None:
                    texts[finding.id] = finish_text(text)
                else:
                    print(f"[explainer] finding {finding.id} replaced: {reason}")
            replaced = len(wanted) - len(texts)
            if replaced:
                status = (f"{replaced} of {len(wanted)} AI explanation(s) did not pass our checks, "
                          "so the standard messages are shown for them." if texts
                          else "The AI explanations did not pass our checks, so the standard messages are shown.")

    explained = [
        ExplainedFinding(
            kind=f.kind, severity=f.severity, title=f.title,
            explanation=texts.get(f.id, f.standard), explained_by_ai=f.id in texts,
            standard_message=f.standard, source=f.source)
        for f in findings
    ]
    notes = list(report.notes)
    if len([f for f in findings if f.use_ai]) > MAX_AI_FINDINGS:
        notes.append(f"Only the {MAX_AI_FINDINGS} most important findings were explained by the AI.")
    return ExplainedReport(summary=build_summary(report), ai_status=status, findings=explained, notes=notes)


def explain_for_user(db: Session, user_id: int, client=None, today: Optional[date] = None) -> ExplainedReport:
    report = check_for_user(db, user_id, today=today)
    return explain_report(db, report, client=client, today=today)
