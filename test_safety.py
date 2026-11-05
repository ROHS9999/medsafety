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
from load_interactions import load_folder
from safety import clean, resolve, split_salts

TODAY = date.today()

# Made-up drug names, so these tests never claim anything about real medicines.
PAIRS = [
    ("drugx", "drugy", "Major"),
    ("drugx", "drugz", "Minor"),
    ("acetaminophen", "drugx", "Moderate"),
    ("drugw", "drugy", "Unknown"),
    ("metformin", "drugy", "Moderate"),
]


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
        for a, b, level in PAIRS:
            first, second = sorted((a, b))
            db.add(models.DrugInteraction(drug_a=first, drug_b=second, level=level))
        db.commit()
    yield SimpleNamespace(client=TestClient(main.app), Session=Session)
    main.app.dependency_overrides.clear()


def login_as(client, email):
    client.post("/signup", json={"email": email, "password": "password123"})
    token = client.post("/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def add_medicine(client, headers, name, salt=None, duration_days=None, start_offset=0):
    pid = client.post("/prescriptions", headers=headers, data={"prescription_date": TODAY.isoformat()}).json()["id"]
    body = {"name": name}
    if duration_days:
        body["duration_days"] = duration_days
        body["start_date"] = (TODAY + timedelta(days=start_offset)).isoformat()
    medicine = client.post(f"/prescriptions/{pid}/medicines", headers=headers, json=body).json()
    if salt is not None:
        assert client.put(f"/medicines/{medicine['id']}/salt", headers=headers, json={"salt_name": salt}).status_code == 200
    return medicine


def report(client, headers):
    response = client.get("/safety/check", headers=headers)
    assert response.status_code == 200
    return response.json()


# ---------- names ----------
@pytest.mark.parametrize("text,expected", [
    ("Ibuprofen + Paracetamol", ["ibuprofen", "paracetamol"]),
    ("Amoxicillin / Clavulanic Acid", ["amoxicillin", "clavulanic acid"]),
    ("Paracetamol 650 mg", ["paracetamol"]),
    ("  ", []),
])
def test_split_salts(text, expected):
    assert split_salts(text) == expected


def test_clean_removes_strengths_and_spaces():
    assert clean("  Metformin   500 mg. ") == "metformin"


def test_resolve_tries_other_spellings():
    known = {"acetaminophen", "metformin", "salbutamol", "amlodipine", "calcium carbonate"}
    assert resolve("Paracetamol", known) == "acetaminophen"
    assert resolve("Metformin Hydrochloride", known) == "metformin"
    assert resolve("Amlodipine Besylate", known) == "amlodipine"
    assert resolve("Salbutamol", known) == "salbutamol"          # already spelled the same way
    assert resolve("Calcium Carbonate", known) == "calcium carbonate"   # a real name is not cut up
    assert resolve("Cilnidipine", known) is None


# ---------- the check ----------
def test_an_interaction_is_found_with_its_severity(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Medicine One", "DrugX")
    add_medicine(env.client, h, "Medicine Two", "DrugY")
    result = report(env.client, h)
    assert len(result["interactions"]) == 1
    warning = result["interactions"][0]
    assert warning["severity"] == "Major" and warning["source"] == "DDInter"
    assert "MAJOR" in warning["message"] and "doctor or pharmacist" in warning["message"]
    assert {c["name"] for c in result["checked"]} == {"Medicine One", "Medicine Two"}


def test_the_most_serious_come_first(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "A", "DrugX")
    add_medicine(env.client, h, "B", "DrugZ")       # minor with A
    add_medicine(env.client, h, "C", "DrugY")       # major with A
    assert [w["severity"] for w in report(env.client, h)["interactions"]] == ["Major", "Minor"]


def test_an_unrated_interaction_says_so(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "A", "DrugW")
    add_medicine(env.client, h, "B", "DrugY")
    result = report(env.client, h)
    assert result["interactions"] == []                          # not mixed in with the rated ones
    warning = result["unrated"][0]
    assert warning["severity"] == "Unknown" and "not been rated" in warning["message"]
    assert any("without a severity rating" in note for note in result["notes"])


def test_a_different_spelling_still_finds_the_interaction(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Dolo 650", "Paracetamol")          # the data says acetaminophen
    add_medicine(env.client, h, "Medicine One", "DrugX")
    warning = report(env.client, h)["interactions"][0]
    assert warning["severity"] == "Moderate" and {warning["salt_a"], warning["salt_b"]} == {"paracetamol", "drugx"}   # shown the way the person typed it


def test_the_salt_form_is_ignored(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Glycomet", "Metformin Hydrochloride")
    add_medicine(env.client, h, "Medicine Two", "DrugY")
    assert report(env.client, h)["interactions"][0]["severity"] == "Moderate"


def test_a_combination_medicine_is_checked_per_salt_but_not_against_itself(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Combo", "DrugX + DrugY")           # these two interact, but they are in one medicine
    assert report(env.client, h)["interactions"] == []
    add_medicine(env.client, h, "Other", "DrugZ")
    severities = [w["severity"] for w in report(env.client, h)["interactions"]]
    assert severities == ["Minor"]                                    # DrugX with DrugZ only


def test_the_same_salt_in_two_medicines_is_a_duplicate_not_an_interaction(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Dolo 650", "Paracetamol")
    add_medicine(env.client, h, "Crocin", "paracetamol")
    result = report(env.client, h)
    assert result["interactions"] == []
    assert len(result["duplicates"]) == 1
    assert set(result["duplicates"][0]["medicines"]) == {"Dolo 650", "Crocin"}
    assert "both contain" in result["duplicates"][0]["message"]


def test_a_duplicate_is_found_even_when_the_salt_is_not_in_the_data(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Lndip", "Cilnidipine")
    add_medicine(env.client, h, "Cilacar", "Cilnidipine")
    result = report(env.client, h)
    assert len(result["duplicates"]) == 1 and len(result["not_checked"]) == 2


def test_a_medicine_without_a_salt_is_listed_as_not_checked(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Mystery")
    add_medicine(env.client, h, "Medicine One", "DrugX")
    result = report(env.client, h)
    assert [n["name"] for n in result["not_checked"]] == ["Mystery"]
    assert "No salt name" in result["not_checked"][0]["reason"]
    assert any("could not be fully checked" in note for note in result["notes"])


def test_a_salt_that_is_not_in_the_data_is_said_out_loud(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Lndip", "Cilnidipine")
    result = report(env.client, h)
    assert "not in the interaction data" in result["not_checked"][0]["reason"]


def test_part_of_a_combination_that_is_not_in_the_data_is_mentioned(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Combo", "DrugX + Madeupine")
    result = report(env.client, h)
    assert result["checked"][0]["salts"] == ["drugx"]
    assert any("madeupine" in note for note in result["notes"])


def test_no_interaction_never_says_safe(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "A", "DrugX")
    result = report(env.client, h)
    assert result["interactions"] == []
    assert any("does not mean the medicines are safe" in note for note in result["notes"])


def test_only_current_confirmed_medicines_are_checked(env):
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "Current", "DrugX")
    add_medicine(env.client, h, "Finished", "DrugY", duration_days=2, start_offset=-10)   # ended 9 days ago
    assert report(env.client, h)["interactions"] == []
    with env.Session() as db:                                         # an unconfirmed one
        user_id = db.query(models.User).first().id
        pid = db.query(models.Prescription).first().id
        db.add(models.Medicine(user_id=user_id, prescription_id=pid, name="Unconfirmed", salt_name="DrugY", confirmed=False))
        db.commit()
    assert report(env.client, h)["interactions"] == []


def test_an_empty_interaction_table_tells_you_to_load_it(env):
    with env.Session() as db:
        db.query(models.DrugInteraction).delete()
        db.commit()
    h = login_as(env.client, "meera@example.com")
    add_medicine(env.client, h, "A", "DrugX")
    assert any("load_interactions" in note for note in report(env.client, h)["notes"])


# ---------- setting the salt ----------
def test_the_salt_can_be_set_changed_and_cleared(env):
    h = login_as(env.client, "meera@example.com")
    medicine = add_medicine(env.client, h, "Dolo")
    url = f"/medicines/{medicine['id']}/salt"
    assert env.client.put(url, headers=h, json={"salt_name": "  Paracetamol  "}).json()["salt_name"] == "Paracetamol"
    assert env.client.put(url, headers=h, json={"salt_name": ""}).json()["salt_name"] is None
    assert env.client.put(url, headers=h, json={"salt_name": "x" * 201}).status_code == 422


# ---------- privacy ----------
def test_people_only_see_their_own_medicines_in_the_check(env):
    meera = login_as(env.client, "meera@example.com")
    ravi = login_as(env.client, "ravi@example.com")
    medicine = add_medicine(env.client, meera, "Medicine One", "DrugX")
    add_medicine(env.client, ravi, "Medicine Two", "DrugY")
    assert report(env.client, ravi)["interactions"] == []
    assert [c["name"] for c in report(env.client, ravi)["checked"]] == ["Medicine Two"]
    assert env.client.put(f"/medicines/{medicine['id']}/salt", headers=ravi, json={"salt_name": "HACK"}).status_code == 404


def test_the_new_pages_need_login(env):
    assert env.client.get("/safety/check").status_code == 401
    assert env.client.put("/medicines/1/salt", json={"salt_name": "x"}).status_code == 401


# ---------- loading the data ----------
def test_the_loader_cleans_and_keeps_the_most_serious(tmp_path, env):
    (tmp_path / "DDIndex_a.csv").write_text(
        "DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level\n"
        "1,Alpha,2,Beta,Minor\n"
        "2,Beta,1,Alpha,Major\n"           # same pair the other way round, more serious
        "3,Gamma,3,Gamma,Major\n"          # a drug with itself: skipped
        "4, delta ,5,EPSILON,Strange\n",   # odd level: becomes Unknown
        encoding="utf-8-sig")
    with env.Session() as db:
        result = load_folder(db, tmp_path)
        assert result["pairs"] == 2
        rows = {(r.drug_a, r.drug_b): r.level for r in db.query(models.DrugInteraction).all()}
    assert rows == {("alpha", "beta"): "Major", ("delta", "epsilon"): "Unknown"}


def test_the_loader_says_clearly_when_the_folder_is_wrong(tmp_path, env):
    with env.Session() as db:
        with pytest.raises(FileNotFoundError):
            load_folder(db, tmp_path)
