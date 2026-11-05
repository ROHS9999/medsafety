from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import reading_job
from database import Base, get_db
from durations import suggest_days
from reader import PrescriptionRead, ReadMedicine

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image"
REAL_SCHEDULE = reading_job.schedule_reading
TODAY = date.today()


def med(written, name, strength=None, dose=None, frequency=None, duration=None, unclear=False):
    return ReadMedicine(written_text=written, name=name, strength=strength, dose=dose,
                        frequency=frequency, duration=duration, unclear=unclear)


def reading():
    return PrescriptionRead(medicine_lines_on_page=None, prescription_date="05/10/2026", doctor_name="Dr. A. Rao", medicines=[
        med("1. Tab Dolo 650 mg 1-1-1 x 5 days", "Tab Dolo", "650 mg", None, "1-1-1", "x 5 days"),
        med("2. Tab Thyronorm 50 mcg 1 OD Continue", "Tab Thyronorm", "50 mcg", None, "1 OD", "Continue"),
        med("3. Tab Pan 40 mg OD x 10 days", "Tab Pan", "40 mg", "1", "OD", "x 10 days"),   # dose "1" is invented
    ])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(reading_job, "SessionLocal", TestSession)
    monkeypatch.setattr(reading_job, "schedule_reading", REAL_SCHEDULE)
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: reading())
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def login_as(client, email):
    client.post("/signup", json={"email": email, "password": "password123"})
    token = client.post("/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers):
    response = client.post("/prescriptions", headers=headers, data={"prescription_date": TODAY.isoformat()},
                           files={"file": ("rx.png", PNG, "image/png")})
    pid = response.json()["id"]
    meds = {m["name"]: m for m in client.get(f"/prescriptions/{pid}/medicines", headers=headers).json()}
    return pid, meds


def current_names(client, headers):
    return sorted(m["name"] for m in client.get("/medicines/current", headers=headers).json())


# ---------- reading the duration ----------
@pytest.mark.parametrize("text,expected", [
    ("x 5 days", 5), ("5 days", 5), ("for 5 days", 5), ("5d", 5), ("x 10 days", 10),
    ("x 2 wks", 14), ("2 weeks", 14), ("x 1 mth", 30), ("1 month", 30), ("x 3 months", 90),
    ("Continue", None), ("SOS", None), ("", None), (None, None),
    ("3 days / 5 days", None), ("0 days", None), ("1000 days", None), ("x 5", None),
])
def test_suggest_days(text, expected):
    assert suggest_days(text) == expected


# ---------- confirming one medicine ----------
def test_a_clean_medicine_can_be_confirmed_as_read_and_gets_dates(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    assert meds["Tab Dolo"]["suggested_duration_days"] == 5

    response = client.post(f"/medicines/{meds['Tab Dolo']['id']}/confirm", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is True and body["duration_days"] == 5
    assert body["start_date"] == TODAY.isoformat()
    assert body["end_date"] == (TODAY + timedelta(days=4)).isoformat()
    assert current_names(client, headers) == ["Tab Dolo"]


def test_a_medicine_with_no_clear_duration_is_confirmed_as_long_term(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    body = client.post(f"/medicines/{meds['Tab Thyronorm']['id']}/confirm", headers=headers).json()
    assert body["duration_days"] is None and body["end_date"] is None
    assert current_names(client, headers) == ["Tab Thyronorm"]


def test_a_flagged_medicine_cannot_be_confirmed_as_read(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    assert meds["Tab Pan"]["unclear"] is True and meds["Tab Pan"]["problems"]
    response = client.post(f"/medicines/{meds['Tab Pan']['id']}/confirm", headers=headers)
    assert response.status_code == 409 and "flagged" in response.json()["detail"]
    assert current_names(client, headers) == []


def test_a_flagged_medicine_can_be_fixed_and_confirmed_in_one_step(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    pan = meds["Tab Pan"]["id"]
    fixed = {"name": "Tab Pan", "strength": "40 mg", "dose": "1 tablet", "frequency": "OD", "duration_days": 10}
    response = client.put(f"/medicines/{pan}?confirm=true", headers=headers, json=fixed)
    body = response.json()
    assert response.status_code == 200 and body["confirmed"] is True
    assert body["unclear"] is False and body["problems"] == []
    assert body["dose"] == "1 tablet" and body["end_date"] == (TODAY + timedelta(days=9)).isoformat()
    assert body["written_text"] == "3. Tab Pan 40 mg OD x 10 days"      # what was written is never lost


def test_editing_without_confirm_keeps_it_unconfirmed_but_clears_the_flag(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    pan = meds["Tab Pan"]["id"]
    body = client.put(f"/medicines/{pan}", headers=headers, json={"name": "Tab Pan", "dose": "1 tablet"}).json()
    assert body["confirmed"] is False and body["unclear"] is False
    assert current_names(client, headers) == []
    assert client.post(f"/medicines/{pan}/confirm", headers=headers).status_code == 200


def test_confirming_twice_is_refused(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    dolo = meds["Tab Dolo"]["id"]
    client.post(f"/medicines/{dolo}/confirm", headers=headers)
    assert client.post(f"/medicines/{dolo}/confirm", headers=headers).status_code == 409


def test_a_wrong_medicine_can_be_deleted_and_a_missing_one_added(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    assert client.delete(f"/medicines/{meds['Tab Pan']['id']}", headers=headers).status_code == 204
    added = client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": "Cap Azithral", "duration_days": 3})
    assert added.status_code == 201 and added.json()["confirmed"] is True
    assert current_names(client, headers) == ["Cap Azithral"]


# ---------- confirming the whole list ----------
def test_the_whole_list_cannot_be_confirmed_while_something_is_flagged(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    response = client.post(f"/prescriptions/{pid}/confirm", headers=headers, json={"nothing_is_missing": True})
    assert response.status_code == 409 and str(meds["Tab Pan"]["id"]) in response.json()["detail"]
    assert current_names(client, headers) == []


def test_the_person_must_say_nothing_is_missing(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    client.delete(f"/medicines/{meds['Tab Pan']['id']}", headers=headers)
    assert client.post(f"/prescriptions/{pid}/confirm", headers=headers, json={"nothing_is_missing": False}).status_code == 400
    assert client.post(f"/prescriptions/{pid}/confirm", headers=headers, json={}).status_code == 422


def test_confirming_the_whole_list_confirms_everything_left(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    client.put(f"/medicines/{meds['Tab Pan']['id']}?confirm=true", headers=headers,
               json={"name": "Tab Pan", "dose": "1 tablet", "duration_days": 10})
    response = client.post(f"/prescriptions/{pid}/confirm", headers=headers, json={"nothing_is_missing": True})
    assert response.status_code == 200 and response.json()["list_confirmed"] is True
    assert current_names(client, headers) == ["Tab Dolo", "Tab Pan", "Tab Thyronorm"]


def test_reading_again_makes_the_list_unconfirmed_again(client):
    headers = login_as(client, "meera@example.com")
    pid, meds = upload(client, headers)
    client.delete(f"/medicines/{meds['Tab Pan']['id']}", headers=headers)
    client.post(f"/prescriptions/{pid}/confirm", headers=headers, json={"nothing_is_missing": True})
    assert client.get(f"/prescriptions/{pid}", headers=headers).json()["list_confirmed"] is True
    client.post(f"/prescriptions/{pid}/read", headers=headers)
    assert client.get(f"/prescriptions/{pid}", headers=headers).json()["list_confirmed"] is False
    assert current_names(client, headers) == ["Tab Dolo", "Tab Thyronorm"]      # confirmed ones stay


# ---------- privacy ----------
def test_other_people_cannot_confirm_or_edit_my_medicines(client):
    meera = login_as(client, "meera@example.com")
    ravi = login_as(client, "ravi@example.com")
    pid, meds = upload(client, meera)
    dolo = meds["Tab Dolo"]["id"]
    assert client.post(f"/medicines/{dolo}/confirm", headers=ravi).status_code == 404
    assert client.put(f"/medicines/{dolo}?confirm=true", headers=ravi, json={"name": "HACK"}).status_code == 404
    assert client.post(f"/prescriptions/{pid}/confirm", headers=ravi, json={"nothing_is_missing": True}).status_code == 404
    assert current_names(client, meera) == []


def test_the_new_pages_need_login(client):
    assert client.post("/medicines/1/confirm").status_code == 401
    assert client.post("/prescriptions/1/confirm", json={"nothing_is_missing": True}).status_code == 401
