import pytest

import reading_job


@pytest.fixture(autouse=True)
def no_reading_unless_a_test_asks(monkeypatch):
    """By default, no test starts a reading or calls Google."""
    monkeypatch.setattr(reading_job, "schedule_reading", lambda background_tasks, prescription_id: None)
