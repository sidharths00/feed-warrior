import os
import pytest
from feed_warrior.config import Config


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("APIFY_TOKEN", "apify-x")
    monkeypatch.setenv("RESEND_API_KEY", "re-x")
    monkeypatch.setenv("RECIPIENT_EMAIL", "me@example.com")
    monkeypatch.setenv("CRON_SECRET", "secret")
    monkeypatch.setenv("USER_HANDLE", "sidharths00")
    monkeypatch.setenv("KEYWORDS", "a, b ,c")
    monkeypatch.setenv("BUCKET_WEIGHTS", '{"signal":0.6,"work_adjacent":0.3,"discourse":0.1}')
    monkeypatch.setenv("DAILY_SLOTS", "5")
    cfg = Config.from_env()
    assert cfg.user_handle == "sidharths00"
    assert cfg.keywords == ["a", "b", "c"]
    assert cfg.bucket_weights == {"signal": 0.6, "work_adjacent": 0.3, "discourse": 0.1}
    assert cfg.daily_slots == 5


def test_config_weights_must_sum_to_one(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "x"); monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("APIFY_TOKEN", "x"); monkeypatch.setenv("RESEND_API_KEY", "x")
    monkeypatch.setenv("RECIPIENT_EMAIL", "x"); monkeypatch.setenv("CRON_SECRET", "x")
    monkeypatch.setenv("USER_HANDLE", "x"); monkeypatch.setenv("KEYWORDS", "x")
    monkeypatch.setenv("BUCKET_WEIGHTS", '{"signal":0.5,"work_adjacent":0.3,"discourse":0.5}')
    monkeypatch.setenv("DAILY_SLOTS", "5")
    with pytest.raises(ValueError, match="must sum to 1"):
        Config.from_env()
