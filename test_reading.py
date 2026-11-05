import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import reading_job
from database import Base, get_db
from reader import PrescriptionRead, ReadMedicine

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image"
REAL_SCHEDULE = reading_job.schedule_reading   # the real one, before conftest switches it off


def med(written, name, strength=None, dose=None, frequency=None, duration=None, unclear=False):
    return ReadMedicine(
        written_text=written, name=name, strength=strength, dose=dose,
        frequency=frequency, duration=duration, unclear=unclear,
    )


def good_reading():
    return PrescriptionRead(medicine_lines_on_page=None, 
        prescription_date="05/10/2026",
        doctor_name="Dr. A. Rao",
        medicines=[
            med("1. Tab Dolo 650 mg 1-1-1 after food x 5 days", "Tab Dolo", "650 mg", None, "1-1-1 after food", "x 5 days"),
            med("2. Cap Azithral 500 1 OD x 3 days", "Cap Azithral", "500", None, "1 OD", "x 3 days"),
        ],
    )


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
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: good_reading())
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def login_as(client, email):
    client.post("/signup", json={"email": email, "password": "password123"})
    token = client.post("/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, with_file=True):
    files = {"file": ("rx.png", PNG, "image/png")} if with_file else None
    return client.post("/prescriptions", headers=headers, data={"prescription_date": "2026-10-05"}, files=files)


def test_upload_reads_in_the_background_and_saves_unconfirmed_medicines(client):
    headers = login_as(client, "meera@example.com")
    response = upload(client, headers)
    assert response.status_code == 201
    pid = response.json()["id"]

    status = client.get(f"/prescriptions/{pid}", headers=headers).json()
    assert status["reading_status"] == "ready"
    assert status["date_as_written"] == "05/10/2026" and status["doctor_as_written"] == "Dr. A. Rao"

    medicines = client.get(f"/prescriptions/{pid}/medicines", headers=headers).json()
    assert [m["name"] for m in medicines] == ["Tab Dolo", "Cap Azithral"]
    assert all(m["confirmed"] is False for m in medicines)
    assert medicines[0]["frequency"] == "1-1-1 after food" and medicines[0]["duration_text"] == "x 5 days"
    assert medicines[0]["written_text"].startswith("1. Tab Dolo")


def test_unconfirmed_medicines_are_not_current_until_confirmed(client):
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    assert client.get("/medicines/current", headers=headers).json() == []
    client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": "Typed by hand"})
    assert [m["name"] for m in client.get("/medicines/current", headers=headers).json()] == ["Typed by hand"]


def test_an_invented_value_is_removed_and_the_medicine_is_flagged(client, monkeypatch):
    invented = PrescriptionRead(medicine_lines_on_page=None, prescription_date="05/10/2026", doctor_name=None, medicines=[
        med("5. Provigor-HP Powder x 1 mth", "Provigor-HP Powder", dose="typically 2 scoops", duration="x 1 mth")])
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: invented)
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    saved = client.get(f"/prescriptions/{pid}/medicines", headers=headers).json()[0]
    assert saved["dose"] is None and saved["duration_text"] == "x 1 mth"
    assert saved["unclear"] is True and any("dose" in p for p in saved["problems"])


def test_a_failed_reading_shows_a_safe_message(client, monkeypatch):
    def too_busy(path):
        raise errors.ServerError(503, {"error": {"code": 503, "message": "overloaded C:\\secret\\key", "status": "UNAVAILABLE"}})
    monkeypatch.setattr(reading_job, "read_with_ai", too_busy)
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    status = client.get(f"/prescriptions/{pid}", headers=headers).json()
    assert status["reading_status"] == "failed"
    assert "busy" in status["reading_error"] and "secret" not in status["reading_error"]
    assert client.get(f"/prescriptions/{pid}/medicines", headers=headers).json() == []


def test_a_file_path_never_leaks_in_an_error(client, monkeypatch):
    def broken(path):
        raise ValueError("File not found: C:\\Users\\Rohan\\secret\\rx.png")
    monkeypatch.setattr(reading_job, "read_with_ai", broken)
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    error = client.get(f"/prescriptions/{pid}", headers=headers).json()["reading_error"]
    assert "Rohan" not in error and "secret" not in error


def test_reading_again_replaces_the_old_reading_but_keeps_confirmed_medicines(client, monkeypatch):
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    client.post(f"/prescriptions/{pid}/medicines", headers=headers, json={"name": "Typed by hand"})
    again = client.post(f"/prescriptions/{pid}/read", headers=headers)
    assert again.status_code == 202
    names = [m["name"] for m in client.get(f"/prescriptions/{pid}/medicines", headers=headers).json()]
    assert sorted(names) == ["Cap Azithral", "Tab Dolo", "Typed by hand"]


def test_reading_again_after_a_failure_works(client, monkeypatch):
    calls = {"n": 0}
    def first_fails(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise errors.ServerError(504, {"error": {"code": 504, "message": "x", "status": "DEADLINE_EXCEEDED"}})
        return good_reading()
    monkeypatch.setattr(reading_job, "read_with_ai", first_fails)
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    assert client.get(f"/prescriptions/{pid}", headers=headers).json()["reading_status"] == "failed"
    client.post(f"/prescriptions/{pid}/read", headers=headers)
    status = client.get(f"/prescriptions/{pid}", headers=headers).json()
    assert status["reading_status"] == "ready" and status["reading_error"] is None


def test_no_file_means_no_reading(client, monkeypatch):
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: pytest.fail("the reader must not be called"))
    headers = login_as(client, "meera@example.com")
    response = upload(client, headers, with_file=False)
    assert response.json()["reading_status"] == "none"
    assert client.post(f"/prescriptions/{response.json()['id']}/read", headers=headers).status_code == 400


def test_other_people_cannot_see_or_start_a_reading(client):
    meera = login_as(client, "meera@example.com")
    ravi = login_as(client, "ravi@example.com")
    pid = upload(client, meera).json()["id"]
    assert client.get(f"/prescriptions/{pid}", headers=ravi).status_code == 404
    assert client.post(f"/prescriptions/{pid}/read", headers=ravi).status_code == 404
    assert client.get(f"/prescriptions/{pid}", headers=meera).status_code == 200


def test_the_pages_need_login(client):
    assert client.get("/prescriptions/1").status_code == 401
    assert client.post("/prescriptions/1/read").status_code == 401


def test_too_many_medicines_and_very_long_text_are_limited(client, monkeypatch):
    many = PrescriptionRead(medicine_lines_on_page=None, prescription_date="x" * 500, doctor_name=None,
                            medicines=[med(f"Tab Drug{i}", f"Tab Drug{i}") for i in range(50)])
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: many)
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    assert len(client.get(f"/prescriptions/{pid}/medicines", headers=headers).json()) == 30
    assert len(client.get(f"/prescriptions/{pid}", headers=headers).json()["date_as_written"]) == 100


def test_a_missing_medicine_note_is_saved_and_cleared_on_a_good_reading(client, monkeypatch):
    short = PrescriptionRead(medicine_lines_on_page=5, prescription_date="6/6/", doctor_name=None,
                             medicines=[med("1. Tab Dolo 650", "Tab Dolo")])
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: short)
    headers = login_as(client, "meera@example.com")
    pid = upload(client, headers).json()["id"]
    note = client.get(f"/prescriptions/{pid}", headers=headers).json()["reading_note"]
    assert "5 medicines" in note and "6/6/" in note

    fixed = PrescriptionRead(medicine_lines_on_page=1, prescription_date="05/10/2026", doctor_name=None,
                             medicines=[med("1. Tab Dolo 650", "Tab Dolo")])
    monkeypatch.setattr(reading_job, "read_with_ai", lambda path: fixed)
    client.post(f"/prescriptions/{pid}/read", headers=headers)
    assert client.get(f"/prescriptions/{pid}", headers=headers).json()["reading_note"] is None
