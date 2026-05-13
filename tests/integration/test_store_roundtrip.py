import os
from datetime import datetime, timezone
import pytest
from feed_warrior.store import Store, Tweet

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")


def test_migrate_creates_tables(db_pool):
    store = Store(db_pool)
    store.migrate("migrations")
    with db_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.tweets')")
            assert cur.fetchone()[0] == "tweets"


def test_upsert_tweet_roundtrip(db_pool):
    store = Store(db_pool)
    store.migrate("migrations")
    t = Tweet(
        id="123",
        author_handle="karpathy",
        text="hello world",
        url="https://x.com/karpathy/status/123",
        posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        source="list",
    )
    store.upsert_tweets([t])
    fetched = store.get_recent_tweets(since=datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert len(fetched) == 1
    assert fetched[0].id == "123"
    assert fetched[0].author_handle == "karpathy"


def test_upsert_tweet_dedup(db_pool):
    store = Store(db_pool)
    store.migrate("migrations")
    t = Tweet(id="1", author_handle="a", text="x", url="u", posted_at=datetime.now(timezone.utc), source="list")
    store.upsert_tweets([t, t])
    assert len(store.get_recent_tweets(since=datetime(2020, 1, 1, tzinfo=timezone.utc))) == 1
