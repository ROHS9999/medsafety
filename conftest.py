import pytest

import explainer
import reading_job


@pytest.fixture(autouse=True)
def no_reading_unless_a_test_asks(monkeypatch):
    """By default, no test starts a reading or calls Google."""
    monkeypatch.setattr(reading_job, "schedule_reading", lambda background_tasks, prescription_id: None)


@pytest.fixture(autouse=True)
def no_ai_explanations_unless_a_test_asks(monkeypatch):
    """By default, no test asks the AI for an explanation. Also start every test with an empty memory."""
    monkeypatch.setattr(explainer, "make_client", lambda: None)
    explainer._cache.clear()
    explainer._calls.update({"day": None, "count": 0})
