from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal
import json

from psycopg.rows import class_row
from psycopg_pool import ConnectionPool


@dataclass
class Tweet:
    id: str
    author_handle: str
    text: str
    url: str
    posted_at: datetime
    source: Literal["list", "search"]
    fetched_at: datetime | None = None


@dataclass
class VoiceSample:
    id: str
    text: str
    posted_at: datetime


@dataclass
class DigestItem:
    digest_id: int
    tweet_id: str
    draft_text: str
    why_interesting: str
    scores: dict


class Store:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def migrate(self, migrations_dir: str) -> None:
        path = Path(migrations_dir)
        files = sorted(path.glob("*.sql"))
        with self.pool.connection() as conn:
            for f in files:
                conn.execute(f.read_text())
            conn.commit()

    def upsert_tweets(self, tweets: Iterable[Tweet]) -> int:
        sql = """
            INSERT INTO tweets (id, author_handle, text, url, posted_at, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """
        rows = [(t.id, t.author_handle, t.text, t.url, t.posted_at, t.source) for t in tweets]
        if not rows:
            return 0
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
                inserted = cur.rowcount
            conn.commit()
        return inserted

    def get_recent_tweets(self, since: datetime) -> list[Tweet]:
        sql = "SELECT id, author_handle, text, url, posted_at, source, fetched_at FROM tweets WHERE posted_at >= %s ORDER BY posted_at DESC"
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=class_row(Tweet)) as cur:
                cur.execute(sql, (since,))
                return cur.fetchall()

    def upsert_voice_samples(self, samples: Iterable[VoiceSample]) -> int:
        sql = "INSERT INTO voice_samples (id, text, posted_at) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING"
        rows = [(s.id, s.text, s.posted_at) for s in samples]
        if not rows:
            return 0
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
                inserted = cur.rowcount
            conn.commit()
        return inserted

    def get_voice_samples(self, limit: int = 200) -> list[VoiceSample]:
        sql = "SELECT id, text, posted_at FROM voice_samples ORDER BY posted_at DESC LIMIT %s"
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=class_row(VoiceSample)) as cur:
                cur.execute(sql, (limit,))
                return cur.fetchall()

    def upsert_accounts(self, handles: Iterable[str]) -> int:
        sql = "INSERT INTO accounts (handle) VALUES (%s) ON CONFLICT (handle) DO UPDATE SET active = TRUE"
        rows = [(h,) for h in handles]
        if not rows:
            return 0
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
                inserted = cur.rowcount
            conn.commit()
        return inserted

    def get_active_accounts(self) -> list[str]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT handle FROM accounts WHERE active ORDER BY handle")
                return [r[0] for r in cur.fetchall()]

    def create_digest(self, status: str = "sent") -> int:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO digests (status) VALUES (%s) RETURNING id", (status,))
                digest_id = cur.fetchone()[0]
            conn.commit()
        return digest_id

    def add_digest_items(self, items: Iterable[DigestItem]) -> None:
        sql = "INSERT INTO digest_items (digest_id, tweet_id, draft_text, why_interesting, scores) VALUES (%s, %s, %s, %s, %s)"
        rows = [(i.digest_id, i.tweet_id, i.draft_text, i.why_interesting, json.dumps(i.scores)) for i in items]
        if not rows:
            return
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()

    def log_error(self, component: str, message: str, context: dict | None = None) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO errors (component, message, context) VALUES (%s, %s, %s)",
                    (component, message, json.dumps(context) if context else None),
                )
            conn.commit()
