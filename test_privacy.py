import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from database import Base, get_db

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A fresh, empty database and upload folder for every test.
    Your real medsafety.db is never touched."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def login_as(client, email):
    client.post("/signup", json={"email": email, "password": "password123"})
    response = client.post("/login", data={"username": email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_everything(client, headers):
    """Meera saves one of every kind of record. Returns their ids."""
    ids = {}
    client.put("/profile", headers=headers, json={"full_name": "Meera", "age": 45})
    ids["condition"] = client.post(
        "/conditions", headers=headers, json={"name": "Asthma", "acuity_type": "chronic"}
    ).json()["id"]
    ids["allergy"] = client.post(
        "/allergies", headers=headers, json={"substance": "Penicillin"}
    ).json()["id"]
    ids["lab"] = client.post(
        "/labs", headers=headers, json={"test_name": "eGFR", "value": 58, "taken_on": "2026-01-10"}
    ).json()["id"]
    ids["doctor"] = client.post("/doctors", headers=headers, json={"name": "Dr. Rao"}).json()["id"]
    ids["prescription"] = client.post(
        "/prescriptions",
        headers=headers,
        data={"prescription_date": "2026-01-01", "doctor_id": str(ids["doctor"])},
        files={"file": ("rx.png", PNG, "image/png")},
    ).json()["id"]
    ids["medicine"] = client.post(
        f"/prescriptions/{ids['prescription']}/medicines", headers=headers, json={"name": "Dolo 650"}
    ).json()["id"]
    return ids


# Every page that must be locked: (method, path)
LOCKED_PAGES = [
    ("GET", "/me"),
    ("GET", "/profile"),
    ("PUT", "/profile"),
    ("GET", "/conditions"),
    ("POST", "/conditions"),
    ("PUT", "/conditions/1"),
    ("DELETE", "/conditions/1"),
    ("GET", "/allergies"),
    ("POST", "/allergies"),
    ("PUT", "/allergies/1"),
    ("DELETE", "/allergies/1"),
    ("GET", "/labs"),
    ("GET", "/labs/latest"),
    ("POST", "/labs"),
    ("PUT", "/labs/1"),
    ("DELETE", "/labs/1"),
    ("GET", "/doctors"),
    ("POST", "/doctors"),
    ("PUT", "/doctors/1"),
    ("DELETE", "/doctors/1"),
    ("GET", "/prescriptions"),
    ("POST", "/prescriptions"),
    ("GET", "/prescriptions/1/file"),
    ("DELETE", "/prescriptions/1"),
    ("GET", "/prescriptions/1/medicines"),
    ("POST", "/prescriptions/1/medicines"),
    ("GET", "/medicines/current"),
    ("PUT", "/medicines/1"),
    ("DELETE", "/medicines/1"),
]


@pytest.mark.parametrize("method,path", LOCKED_PAGES)
def test_page_is_locked_without_login(client, method, path):
    assert client.request(method, path).status_code == 401, f"{method} {path} is not locked"


def test_a_fake_login_token_is_refused(client):
    fake = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/conditions", headers=fake).status_code == 401


def test_other_person_cannot_see_or_change_my_data(client):
    meera = login_as(client, "meera@example.com")
    ravi = login_as(client, "ravi@example.com")
    ids = create_everything(client, meera)

    # Ravi looks at the lists: he must see nothing of Meera's.
    for path in [
        "/conditions", "/allergies", "/labs", "/labs/latest", "/doctors",
        "/prescriptions", "/medicines/current",
    ]:
        response = client.get(path, headers=ravi)
        assert response.status_code == 200 and response.json() == [], f"Ravi can see {path}"
    assert client.get("/profile", headers=ravi).status_code == 404

    # Ravi tries to open, edit or delete Meera's records by their id: all must say "not found".
    attempts = [
        ("PUT", f"/conditions/{ids['condition']}", {"name": "HACK", "acuity_type": "acute"}),
        ("DELETE", f"/conditions/{ids['condition']}", None),
        ("PUT", f"/allergies/{ids['allergy']}", {"substance": "HACK"}),
        ("DELETE", f"/allergies/{ids['allergy']}", None),
        ("PUT", f"/labs/{ids['lab']}", {"test_name": "HACK", "value": 1, "taken_on": "2026-01-01"}),
        ("DELETE", f"/labs/{ids['lab']}", None),
        ("PUT", f"/doctors/{ids['doctor']}", {"name": "HACK"}),
        ("DELETE", f"/doctors/{ids['doctor']}", None),
        ("GET", f"/prescriptions/{ids['prescription']}/file", None),
        ("DELETE", f"/prescriptions/{ids['prescription']}", None),
        ("GET", f"/prescriptions/{ids['prescription']}/medicines", None),
        ("POST", f"/prescriptions/{ids['prescription']}/medicines", {"name": "HACK"}),
        ("PUT", f"/medicines/{ids['medicine']}", {"name": "HACK"}),
        ("DELETE", f"/medicines/{ids['medicine']}", None),
    ]
    for method, path, body in attempts:
        response = client.request(method, path, headers=ravi, json=body)
        assert response.status_code == 404, f"Ravi got {response.status_code} on {method} {path}"

    # Ravi tries to attach Meera's doctor to his own prescription.
    response = client.post(
        "/prescriptions",
        headers=ravi,
        data={"prescription_date": "2026-01-01", "doctor_id": str(ids["doctor"])},
    )
    assert response.status_code == 404

    # Ravi saves his own profile: it must not change Meera's.
    client.put("/profile", headers=ravi, json={"full_name": "Ravi", "age": 30})

    # After all of that, every one of Meera's records is exactly as she left it.
    assert client.get("/profile", headers=meera).json()["full_name"] == "Meera"
    assert [x["name"] for x in client.get("/conditions", headers=meera).json()] == ["Asthma"]
    assert [x["substance"] for x in client.get("/allergies", headers=meera).json()] == ["Penicillin"]
    assert [x["test_name"] for x in client.get("/labs", headers=meera).json()] == ["eGFR"]
    assert [x["name"] for x in client.get("/doctors", headers=meera).json()] == ["Dr. Rao"]
    assert len(client.get("/prescriptions", headers=meera).json()) == 1
    assert [x["name"] for x in client.get("/medicines/current", headers=meera).json()] == ["Dolo 650"]
    file_response = client.get(f"/prescriptions/{ids['prescription']}/file", headers=meera)
    assert file_response.status_code == 200 and file_response.content == PNG