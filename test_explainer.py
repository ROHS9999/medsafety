import json
import re
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import explainer
import main
import models
from database import Base, get_db
from explainer import CLOSING, build_findings, build_summary, explain_for_user, explain_report, finish_text, problem_with
from safety import DuplicateWarning, SafetyReport

GOOD = "This medicine may not suit you. Please look at it again."


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main, "UPLOAD_DIR", str(tmp_path))
    with Session() as db:
        # the amoxicillin pair only makes 'amoxicillin' a known name
        for a, b, level in [("acetylsalicylic acid", "ibuprofen", "Major"), ("ibuprofen", "metformin", "Moderate"),
                               ("amoxicillin", "warfarin", "Minor")]:     # the last one only makes amoxicillin a known name
            db.add(models.DrugInteraction(drug_a=a, drug_b=b, level=level))
        db.commit()
    yield SimpleNamespace(client=TestClient(main.app), Session=Session)
    main.app.dependency_overrides.clear()


class FakeClient:
    """Pretends to be Gemini. `reply` is a function(list of ids) -> answer text, or an Exception to raise."""
    def __init__(self, reply):
        self.prompts, self.reply = [], reply
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents, config):
        prompt = contents[0]
        self.prompts.append(prompt)
        ids = [int(i) for i in re.findall(r"^\[(\d+)\]", prompt, re.M)]
        result = self.reply(ids) if callable(self.reply) else self.reply
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(text=result)


def answers(texts):
    """texts: {id: text} or a function(id) -> text"""
    def make(ids):
        pick = texts if callable(texts) else texts.get
        return json.dumps({"findings": [{"id": i, "text": pick(i)} for i in ids if pick(i) is not None]})
    return make


def login_as(client, email="meera@example.com"):
    client.post("/signup", json={"email": email, "password": "password123"})
    token = client.post("/login", data={"username": email, "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, client.get("/me", headers=headers).json()["id"]


def scenario(client, headers):
    """Allergy (family), a Major interaction, and two asthma cautions."""
    client.put("/profile", headers=headers, json={"full_name": "Meera Sharma", "age": 45})
    client.post("/allergies", headers=headers, json={"substance": "Penicillin", "severity": "severe"})
    client.post("/conditions", headers=headers, json={"name": "Asthma", "acuity_type": "chronic"})
    pid = client.post("/prescriptions", headers=headers, data={"prescription_date": date.today().isoformat()}).json()["id"]
    for name, salt in [("Augmentin", "Amoxicillin + Clavulanic Acid"), ("Brufen", "Ibuprofen"), ("Ecosprin", "Aspirin")]:
        medicine = client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": name}).json()
        client.put(f"/medicines/{medicine['id']}/salt", headers=headers, json={"salt_name": salt})


def run(env, uid, client):
    with env.Session() as db:
        return explain_for_user(db, uid, client=client)


@pytest.fixture()
def meera(env):
    headers, uid = login_as(env.client)
    scenario(env.client, headers)
    return headers, uid


# ============================================================ the findings
def test_findings_are_in_order_of_importance(env, meera):
    _, uid = meera
    with env.Session() as db:
        from safety import check_for_user
        findings = build_findings(check_for_user(db, uid))
    assert [f.kind for f in findings] == ["allergy", "interaction", "illness", "illness"]
    assert findings[0].severity == "Allergy (same family)" and findings[1].severity == "Major"
    assert [f.id for f in findings] == [1, 2, 3, 4]


def test_the_summary_counts_things_in_plain_words(env, meera):
    _, uid = meera
    with env.Session() as db:
        from safety import check_for_user
        text = build_summary(check_for_user(db, uid))
    assert "1 allergy warning(s)" in text and "1 medicine interaction(s)" in text and "2 illness caution(s)" in text
    assert text.endswith("doctor or pharmacist.")


def test_an_empty_report_says_nothing_was_found(env):
    _, uid = login_as(env.client)
    result = run(env, uid, FakeClient(lambda ids: pytest.fail("nothing to explain")))
    assert result.summary == "We did not find any warnings in what we could check."
    assert result.findings == [] and result.ai_status == "Nothing needed an AI explanation."


# ============================================================ good AI text
def test_good_ai_text_is_used_and_our_advice_is_added(env, meera):
    _, uid = meera
    fake = FakeClient(answers(lambda i: GOOD))
    result = run(env, uid, fake)
    assert result.ai_status == "ok" and len(fake.prompts) == 1
    assert all(f.explained_by_ai for f in result.findings)
    assert all(f.explanation == GOOD + " " + CLOSING for f in result.findings)
    assert result.findings[1].severity == "Major"                      # the label comes from our code
    assert result.findings[0].standard_message.startswith("You listed an allergy to Penicillin")


def test_the_ai_never_sees_the_persons_details(env, meera):
    _, uid = meera
    fake = FakeClient(answers(lambda i: GOOD))
    run(env, uid, fake)
    prompt = fake.prompts[0]
    assert "Meera" not in prompt and "Sharma" not in prompt and "@" not in prompt and "45" not in prompt
    assert "Augmentin" in prompt and "Penicillin" in prompt


def test_the_ai_is_not_sent_the_warnings_that_need_no_rewording(env):
    headers, uid = login_as(env.client)
    pid = env.client.post("/prescriptions", headers=headers, data={"prescription_date": date.today().isoformat()}).json()["id"]
    env.client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": "Mystery"})
    fake = FakeClient(lambda ids: pytest.fail("not for the AI"))
    result = run(env, uid, fake)
    assert fake.prompts == [] and result.findings[0].kind == "not checked" and result.findings[0].explained_by_ai is False


# ============================================================ bad AI text is thrown away
@pytest.mark.parametrize("bad,why", [
    ("This contains warfarin which is risky.", "drug"),
    ("Take 500 mg twice a day.", "number"),
    ("You should stop taking it now.", "stop"),
    ("This is safe to take with food.", "safe"),
    ("This could be fatal.", "danger"),
    ("See https://example.com for more.", "link"),
    ("x" * 600, "long"),
    ("   ", "empty"),
])
def test_bad_text_is_replaced_by_our_standard_message(env, meera, bad, why):
    _, uid = meera
    result = run(env, uid, FakeClient(answers(lambda i: bad if i == 1 else GOOD)))
    first, others = result.findings[0], result.findings[1:]
    assert first.explained_by_ai is False and first.explanation == first.standard_message
    assert all(f.explained_by_ai for f in others)
    assert result.ai_status.startswith("1 of 4")


def test_a_major_interaction_cannot_be_called_minor(env, meera):
    _, uid = meera
    result = run(env, uid, FakeClient(answers(lambda i: "This is only a minor problem." if i == 2 else GOOD)))
    major = result.findings[1]
    assert major.severity == "Major" and major.explained_by_ai is False


def test_a_finding_missing_from_the_ai_answer_gets_the_standard_message(env, meera):
    _, uid = meera
    result = run(env, uid, FakeClient(answers(lambda i: None if i == 3 else GOOD)))
    assert result.findings[2].explained_by_ai is False and result.findings[3].explained_by_ai is True


def test_our_advice_is_not_doubled_when_the_ai_already_wrote_it():
    assert finish_text("It may not suit you. Ask a doctor or pharmacist.") == "It may not suit you. " + CLOSING


def test_numbers_and_drugs_that_are_in_the_facts_are_allowed(env):
    with env.Session() as db:
        pattern = explainer.drug_pattern(db)
    finding = explainer.Finding(id=1, kind="timing", severity="Timing", title="t", standard="s", source=None, use_ai=True, rank=1,
                                facts="Timing: Brufen starts on 2026-11-20 and Ecosprin clears about 2026-11-10. Medicines: ibuprofen and aspirin.")
    assert problem_with("Brufen starts on 20 November, after Ecosprin clears on 10 November. Ibuprofen and aspirin are involved.", finding, pattern) is None
    assert "warfarin" in problem_with("Warfarin is also involved.", finding, pattern)


# ============================================================ when the AI cannot help
def test_garbage_from_the_ai_falls_back_to_standard_messages(env, meera):
    _, uid = meera
    result = run(env, uid, FakeClient("this is not json"))
    assert not any(f.explained_by_ai for f in result.findings)
    assert "could not be used" in result.ai_status and result.findings[0].explanation


def test_a_busy_google_falls_back_without_an_error(env, meera):
    _, uid = meera
    busy = errors.ServerError(503, {"error": {"code": 503, "message": "overloaded C:\\secret", "status": "UNAVAILABLE"}})
    result = run(env, uid, FakeClient(busy))
    assert not any(f.explained_by_ai for f in result.findings)
    assert "busy" in result.ai_status and "secret" not in result.ai_status


def test_the_free_limit_is_explained(env, meera):
    _, uid = meera
    limit = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    assert "limit" in run(env, uid, FakeClient(limit)).ai_status


def test_the_ai_can_be_switched_off(env, meera, monkeypatch):
    _, uid = meera
    monkeypatch.setenv("EXPLAIN_WITH_AI", "off")
    fake = FakeClient(lambda ids: pytest.fail("must not be called"))
    result = run(env, uid, fake)
    assert "switched off" in result.ai_status and fake.prompts == []


def test_without_a_key_the_standard_messages_are_shown(env, meera):
    _, uid = meera
    with env.Session() as db:
        result = explain_for_user(db, uid)             # conftest makes make_client() return None
    assert "No AI key" in result.ai_status and result.findings[0].explanation == result.findings[0].standard_message


# ============================================================ saving calls
def test_the_same_report_is_not_sent_to_the_ai_twice(env, meera):
    _, uid = meera
    fake = FakeClient(answers(lambda i: GOOD))
    run(env, uid, fake)
    again = run(env, uid, fake)
    assert len(fake.prompts) == 1 and all(f.explained_by_ai for f in again.findings)


def test_a_daily_limit_protects_the_free_quota(env, meera, monkeypatch):
    headers, uid = meera
    monkeypatch.setenv("EXPLAIN_DAILY_LIMIT", "1")
    fake = FakeClient(answers(lambda i: GOOD))
    assert run(env, uid, fake).ai_status == "ok"
    pid = env.client.post("/prescriptions", headers=headers, data={"prescription_date": date.today().isoformat()}).json()["id"]
    medicine = env.client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": "Glycomet"}).json()
    env.client.put(f"/medicines/{medicine['id']}/salt", headers=headers, json={"salt_name": "Metformin"})     # a different report
    second = run(env, uid, fake)
    assert "daily limit" in second.ai_status and len(fake.prompts) == 1


def test_only_the_most_important_findings_go_to_the_ai(env):
    with env.Session() as db:
        report = SafetyReport(
            checked=[], not_checked=[], allergy_warnings=[], illness_warnings=[], interactions=[], unrated=[],
            separated=[], still_in_body=[], conditions_counted=[], conditions_ignored=[], notes=[],
            duplicates=[DuplicateWarning(salt=f"salt{n}", medicines=[f"A{n}", f"B{n}"], message=f"A{n} and B{n} both contain salt{n}.")
                        for n in range(1, 31)])
        fake = FakeClient(answers(lambda i: GOOD))
        result = explain_report(db, report, client=fake)
    assert len(re.findall(r"^\[\d+\]", fake.prompts[0], re.M)) == 25
    assert sum(f.explained_by_ai for f in result.findings) == 25 and len(result.findings) == 30
    assert any("Only the 25 most important" in note for note in result.notes)


# ============================================================ the page
def test_the_page_needs_login(env):
    assert env.client.get("/safety/explain").status_code == 401


def test_the_page_explains_only_my_own_report(env, meera, monkeypatch):
    monkeypatch.setattr(explainer, "make_client", lambda: FakeClient(answers(lambda i: GOOD)))
    headers, _ = meera
    ravi, _ = login_as(env.client, "ravi@example.com")
    mine = env.client.get("/safety/explain", headers=headers).json()
    theirs = env.client.get("/safety/explain", headers=ravi).json()
    assert len(mine["findings"]) == 4 and mine["ai_status"] == "ok"
    assert theirs["findings"] == [] and "Penicillin" not in json.dumps(theirs)
