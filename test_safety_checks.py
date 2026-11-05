from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import Base, get_db
from knowledge import Knowledge, load_knowledge
from safety import check_for_user

TODAY = date.today()
FIXED = date(2026, 11, 1)

# Made-up names for the interactions, so these tests never claim anything about real medicines.
PAIRS = [("drugx", "drugy", "Major"), ("drugw", "drugy", "Unknown")]
MADE_UP = Knowledge(
    allergy_families=[],
    illness_rules=[],
    half_lives={
        "drugx": {"hours": 24.0, "override_days": None, "note": ""},
        "drugy": {"hours": 24.0, "override_days": None, "note": ""},
        "slowdrug": {"hours": 168.0, "override_days": None, "note": ""},
        "quickdrug": {"hours": 2.0, "override_days": None, "note": ""},
    },
)


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
        for a, b, level in PAIRS + [("slowdrug", "drugy", "Moderate"), ("drugy", "quickdrug", "Moderate")]:
            first, second = sorted((a, b))
            db.add(models.DrugInteraction(drug_a=first, drug_b=second, level=level))
        db.commit()
    yield SimpleNamespace(client=TestClient(main.app), Session=Session)
    main.app.dependency_overrides.clear()


def login_as(client, email="meera@example.com"):
    client.post("/signup", json={"email": email, "password": "password123"})
    token = client.post("/login", data={"username": email, "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, client.get("/me", headers=headers).json()["id"]


def add_medicine(client, headers, name, salt=None):
    pid = client.post("/prescriptions", headers=headers, data={"prescription_date": TODAY.isoformat()}).json()["id"]
    medicine = client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": name}).json()
    if salt is not None:
        client.put(f"/medicines/{medicine['id']}/salt", headers=headers, json={"salt_name": salt})
    return medicine


def report(client, headers):
    response = client.get("/safety/check", headers=headers)
    assert response.status_code == 200
    return response.json()


def add_allergy(client, headers, substance, severity=None):
    body = {"substance": substance}
    if severity:
        body["severity"] = severity
    assert client.post("/allergies", headers=headers, json=body).status_code == 201


def add_condition(client, headers, name, acuity, status="ongoing"):
    body = {"name": name, "acuity_type": acuity, "status": status}
    if status == "resolved":
        body["resolved_date"] = TODAY.isoformat()
    assert client.post("/conditions", headers=headers, json=body).status_code == 201


# ====================================================== allergies
def test_a_penicillin_allergy_flags_a_medicine_in_the_same_family(env):
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Penicillin", "severe")
    add_medicine(env.client, h, "Augmentin", "Amoxicillin + Clavulanic Acid")
    warnings = report(env.client, h)["allergy_warnings"]
    assert len(warnings) == 1
    assert warnings[0]["match"] == "same family" and warnings[0]["family"] == "penicillins"
    assert warnings[0]["medicine"] == "Augmentin" and "same group" in warnings[0]["message"]


def test_the_same_drug_is_flagged_as_the_same_drug(env):
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Amoxicillin")
    add_medicine(env.client, h, "Mox", "Amoxicillin")
    assert env.client.get("/safety/check", headers=h).json()["allergy_warnings"][0]["match"] == "same drug"


def test_sulpha_is_understood(env):
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Sulpha")
    add_medicine(env.client, h, "Septran", "Sulfamethoxazole + Trimethoprim")
    assert report(env.client, h)["allergy_warnings"][0]["family"] == "sulfonamide antibiotics"


def test_an_aspirin_allergy_flags_aspirin_itself_first_and_other_pain_medicines_as_family(env):
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Aspirin")
    add_medicine(env.client, h, "Brufen", "Ibuprofen")
    add_medicine(env.client, h, "Ecosprin", "Aspirin")
    warnings = report(env.client, h)["allergy_warnings"]
    assert [(w["medicine"], w["match"]) for w in warnings] == [("Ecosprin", "same drug"), ("Brufen", "same family")]


def test_an_allergy_that_is_not_a_medicine_matches_nothing(env):
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Peanuts")
    add_medicine(env.client, h, "Dolo", "Paracetamol")
    assert report(env.client, h)["allergy_warnings"] == []


def test_allergies_are_checked_even_when_the_interaction_table_is_empty(env):
    with env.Session() as db:
        db.query(models.DrugInteraction).delete()
        db.commit()
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Penicillin")
    add_medicine(env.client, h, "Mox", "Amoxicillin")
    result = report(env.client, h)
    assert len(result["allergy_warnings"]) == 1
    assert any("load_interactions" in note for note in result["notes"])


def test_a_medicine_without_a_salt_cannot_be_checked_for_allergies(env):
    h, _ = login_as(env.client)
    add_allergy(env.client, h, "Penicillin")
    add_medicine(env.client, h, "Mystery")
    result = report(env.client, h)
    assert result["allergy_warnings"] == [] and result["not_checked"][0]["name"] == "Mystery"


def test_one_persons_allergy_never_appears_in_anothers_report(env):
    meera, _ = login_as(env.client, "meera@example.com")
    ravi, _ = login_as(env.client, "ravi@example.com")
    add_allergy(env.client, meera, "Penicillin")
    add_medicine(env.client, ravi, "Mox", "Amoxicillin")
    assert report(env.client, ravi)["allergy_warnings"] == []


# ====================================================== illnesses
def test_a_long_term_illness_that_is_ongoing_is_counted(env):
    h, _ = login_as(env.client)
    add_condition(env.client, h, "Asthma", "chronic")
    add_medicine(env.client, h, "Brufen", "Ibuprofen")
    result = report(env.client, h)
    warning = result["illness_warnings"][0]
    assert warning["level"] == "Caution" and warning["because_of"] == "Asthma" and warning["medicine"] == "Brufen"
    assert result["conditions_counted"] == ["Asthma (chronic, ongoing)"]


def test_a_short_term_illness_that_is_over_is_ignored(env):
    h, _ = login_as(env.client)
    add_condition(env.client, h, "Asthma", "acute", status="resolved")      # e.g. one attack, now over
    add_medicine(env.client, h, "Brufen", "Ibuprofen")
    result = report(env.client, h)
    assert result["illness_warnings"] == []
    assert result["conditions_counted"] == [] and "not counted" in result["conditions_ignored"][0]


def test_a_long_term_illness_marked_resolved_still_counts(env):
    h, _ = login_as(env.client)
    add_condition(env.client, h, "Chronic kidney disease", "chronic", status="resolved")
    add_medicine(env.client, h, "Brufen", "Ibuprofen")
    result = report(env.client, h)
    assert len(result["illness_warnings"]) == 1
    assert "long-term illnesses do not simply expire" in result["conditions_counted"][0]


@pytest.mark.parametrize("egfr,expected", [(25, ["Avoid"]), (40, ["Caution"]), (70, [])])
def test_the_kidney_value_changes_the_advice_for_metformin(env, egfr, expected):
    h, _ = login_as(env.client)
    env.client.put("/profile", headers=h, json={"full_name": "Meera", "kidney_egfr": egfr})
    add_medicine(env.client, h, "Glycomet", "Metformin")
    warnings = report(env.client, h)["illness_warnings"]
    assert [w["level"] for w in warnings] == expected                    # one warning, the most serious
    if warnings:
        assert f"eGFR {egfr}" in warnings[0]["because_of"] and "profile" in warnings[0]["because_of"]


def test_a_newer_test_result_beats_the_profile_value(env):
    h, _ = login_as(env.client)
    env.client.put("/profile", headers=h, json={"full_name": "Meera", "kidney_egfr": 25})
    env.client.post("/labs", headers=h, json={"test_name": "eGFR", "value": 80, "taken_on": TODAY.isoformat()})
    add_medicine(env.client, h, "Glycomet", "Metformin")
    assert report(env.client, h)["illness_warnings"] == []


def test_a_kidney_value_below_60_flags_pain_medicines(env):
    h, _ = login_as(env.client)
    env.client.put("/profile", headers=h, json={"full_name": "Meera", "kidney_egfr": 55})
    add_medicine(env.client, h, "Brufen", "Ibuprofen")
    assert report(env.client, h)["illness_warnings"][0]["level"] == "Caution"


def test_pregnancy_from_the_profile_is_used(env):
    h, _ = login_as(env.client)
    add_medicine(env.client, h, "Telma", "Telmisartan")
    assert report(env.client, h)["illness_warnings"] == []
    env.client.put("/profile", headers=h, json={"full_name": "Meera", "is_pregnant": True})
    warning = report(env.client, h)["illness_warnings"][0]
    assert warning["level"] == "Avoid" and "pregnancy" in warning["because_of"]


def test_g6pd_is_understood(env):
    h, _ = login_as(env.client)
    add_condition(env.client, h, "G6PD deficiency", "chronic")
    add_medicine(env.client, h, "Primaquine", "Primaquine")
    assert report(env.client, h)["illness_warnings"][0]["level"] == "Avoid"


def test_an_illness_with_no_rules_is_said_out_loud(env):
    h, _ = login_as(env.client)
    add_condition(env.client, h, "Migraine", "chronic")
    add_medicine(env.client, h, "Dolo", "Paracetamol")
    assert any("No rules exist yet for: Migraine" in note for note in report(env.client, h)["notes"])


# ====================================================== timing
def add_direct(Session, user_id, name, salt, start, end=None, half_life=None):
    with Session() as db:
        pid = db.query(models.Prescription.id).filter_by(user_id=user_id).first()
        if pid is None:
            rx = models.Prescription(user_id=user_id, prescription_date=start)
            db.add(rx)
            db.commit()
            pid = rx.id
        else:
            pid = pid[0]
        db.add(models.Medicine(user_id=user_id, prescription_id=pid, name=name, salt_name=salt, confirmed=True,
                               start_date=start, end_date=end, half_life_hours=half_life))
        db.commit()


def run(env, user_id, today=FIXED, knowledge=MADE_UP):
    with env.Session() as db:
        return check_for_user(db, user_id, today=today, knowledge=knowledge)


def test_two_medicines_at_the_same_time_overlap(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "DrugX", FIXED - timedelta(days=2))
    add_direct(env.Session, uid, "B", "DrugY", FIXED)
    result = run(env, uid)
    assert len(result.interactions) == 1 and "active together" in result.interactions[0].timing


def test_the_idea_taking_b_after_a_has_cleared_is_not_flagged_as_overlapping(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "DrugX", date(2026, 10, 25), end=date(2026, 11, 5))      # 1 day half-life: 5 days washout
    add_direct(env.Session, uid, "B", "DrugY", date(2026, 11, 20))
    result = run(env, uid)
    assert result.interactions == [] and len(result.separated) == 1
    assert "2026-11-20" in result.separated[0].timing and "2026-11-10" in result.separated[0].timing
    assert any("do not overlap in time" in note for note in result.notes)


def test_starting_b_too_soon_after_a_is_flagged_because_a_is_still_in_the_body(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "SlowDrug", date(2026, 10, 10), end=date(2026, 10, 27))   # 7 day half-life: 35 days washout
    add_direct(env.Session, uid, "B", "DrugY", FIXED)
    result = run(env, uid)
    assert len(result.interactions) == 1 and result.separated == []
    assert len(result.still_in_body) == 1 and "2026-12-01" in result.still_in_body[0]


def test_a_course_that_finished_long_ago_is_left_out(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "SlowDrug", date(2026, 6, 1), end=date(2026, 7, 21))      # cleared by late August
    add_direct(env.Session, uid, "B", "DrugY", FIXED)
    result = run(env, uid)
    assert [c.name for c in result.checked] == ["B"] and result.interactions == []


def test_when_the_half_life_is_unknown_it_is_assumed_gone_on_the_last_day_and_says_so(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "DrugW", FIXED - timedelta(days=3), end=FIXED + timedelta(days=5))
    result = run(env, uid)
    assert any("assumed they left on the last day: A" in note for note in result.notes)


def test_aspirin_has_a_longer_washout_from_the_real_table(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "Ecosprin", "Aspirin", date(2026, 10, 1), end=date(2026, 10, 29))
    result = run(env, uid, knowledge=load_knowledge())
    assert len(result.still_in_body) == 1 and "2026-11-05" in result.still_in_body[0]


def test_the_same_salt_is_only_a_duplicate_while_both_are_active(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "Dolo", "QuickDrug", date(2026, 10, 15), end=date(2026, 10, 20))    # gone by 21 Oct
    add_direct(env.Session, uid, "Crocin", "QuickDrug", FIXED)
    assert run(env, uid).duplicates == []
    add_direct(env.Session, uid, "Calpol", "QuickDrug", FIXED)
    assert len(run(env, uid).duplicates) == 1


def test_a_half_life_typed_on_the_medicine_beats_the_table(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "DrugX", date(2026, 10, 20), end=date(2026, 10, 30), half_life=48)   # 10 days washout
    add_direct(env.Session, uid, "B", "DrugY", FIXED)
    assert len(run(env, uid).interactions) == 1


def test_the_washout_is_capped_at_a_year(env):
    _, uid = login_as(env.client)
    add_direct(env.Session, uid, "A", "DrugX", date(2025, 1, 1), end=date(2025, 12, 31), half_life=100000)
    result = run(env, uid, today=date(2027, 1, 5))        # a year and 5 days after the last dose
    assert result.still_in_body == []


# ====================================================== the knowledge tables
def test_the_real_tables_load_and_make_sense():
    k = load_knowledge()
    assert len(k.allergy_families) >= 8 and len(k.illness_rules) >= 10 and len(k.half_lives) >= 20
    assert all(rule["level"] in ("Avoid", "Caution") and rule["drugs"] and rule["why"] for rule in k.illness_rules)
    assert all(f["members"] for f in k.allergy_families)


def write_tables(folder, families=None, rules=None, half_lives=None):
    (folder / "allergy_families.csv").write_text(families or "family,aliases,members,note\npenicillins,penicillin,amoxicillin,\n")
    (folder / "illness_rules.csv").write_text(
        rules or "illness,aliases,drugs,level,egfr_below,why,source\nasthma,asthma,ibuprofen,Caution,,Careful.,test\n")
    (folder / "half_lives.csv").write_text(half_lives or "salt,half_life_hours,washout_days_override,note\nparacetamol,2,,\n")


def test_good_tables_load_from_any_folder(tmp_path):
    write_tables(tmp_path)
    assert load_knowledge(tmp_path).illness_rules[0]["level"] == "Caution"


def test_a_bad_level_gives_a_clear_message(tmp_path):
    write_tables(tmp_path, rules="illness,aliases,drugs,level,egfr_below,why,source\nasthma,asthma,ibuprofen,Maybe,,x,y\n")
    with pytest.raises(ValueError, match="illness_rules.csv row 2.*Avoid or Caution"):
        load_knowledge(tmp_path)


def test_a_bad_number_gives_a_clear_message(tmp_path):
    write_tables(tmp_path, half_lives="salt,half_life_hours,washout_days_override,note\nparacetamol,abc,,\n")
    with pytest.raises(ValueError, match="half_lives.csv row 2.*half_life_hours 'abc' is not a number"):
        load_knowledge(tmp_path)


def test_a_family_without_members_is_refused(tmp_path):
    write_tables(tmp_path, families="family,aliases,members,note\npenicillins,penicillin,,\n")
    with pytest.raises(ValueError, match="allergy_families.csv row 2"):
        load_knowledge(tmp_path)
