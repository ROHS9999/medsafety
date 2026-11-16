from fastapi.testclient import TestClient

import main

ALLOWED = "http://localhost:3000"


def test_a_screen_on_an_allowed_address_may_call_the_backend():
    client = TestClient(main.app)
    answer = client.options("/login", headers={
        "Origin": ALLOWED, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert answer.status_code == 200
    assert answer.headers["access-control-allow-origin"] == ALLOWED
    assert "authorization" in answer.headers["access-control-allow-headers"].lower()


def test_a_normal_call_from_an_allowed_address_gets_the_permission_header():
    answer = TestClient(main.app).get("/health", headers={"Origin": ALLOWED})
    assert answer.status_code == 200 and answer.headers["access-control-allow-origin"] == ALLOWED


def test_another_website_is_not_allowed():
    client = TestClient(main.app)
    answer = client.options("/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert answer.status_code == 400 and "access-control-allow-origin" not in answer.headers
    plain = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in plain.headers


def test_opening_the_door_for_screens_does_not_open_the_private_pages():
    answer = TestClient(main.app).get("/me", headers={"Origin": ALLOWED})
    assert answer.status_code == 401


def test_the_allowed_addresses_can_be_changed_in_the_settings(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    assert main.frontend_origins() == ["http://localhost:3000", "http://localhost:5173"]
    monkeypatch.setenv("FRONTEND_ORIGINS", " https://a.example , https://b.example ,")
    assert main.frontend_origins() == ["https://a.example", "https://b.example"]
    monkeypatch.setenv("FRONTEND_ORIGINS", "")
    assert main.frontend_origins() == []
