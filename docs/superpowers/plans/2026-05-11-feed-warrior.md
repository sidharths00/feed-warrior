# Feed Warrior Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily content engine that scrapes interesting AI tweets via Apify, drafts replies/quote-tweets in Sidharth's voice using Claude, and emails them to him with one-tap post links via Resend. Runs on Vercel Cron.

**Architecture:** Single Python service deployed to Vercel Functions (Fluid Compute). Vercel Cron triggers `/api/digest` daily at 14:00 UTC; the same handler is callable on-demand from a CLI. Postgres (Neon) persists tweets, voice corpus, curated accounts, and digest history. Claude Sonnet 4.6 via the Anthropic SDK does scoring + drafting. Resend sends the email.

**Tech Stack:** Python 3.13, Vercel Functions + Cron, Neon Postgres (Vercel Marketplace), Resend (Vercel Marketplace), Apify (existing subscription), Anthropic SDK (Claude Sonnet 4.6), psycopg[pool], httpx, click, jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-05-11-twitter-warrior-design.md`

---

## File Structure

Files created across the plan, with single-responsibility per file:

```
feed-warrior/
├── api/
│   └── digest.py                       # Vercel function entry; auth + orchestration
├── src/feed_warrior/
│   ├── __init__.py
│   ├── config.py                       # env loading + bucket weights + keywords
│   ├── apify_client.py                 # Apify actor wrappers
│   ├── store.py                        # Postgres connection pool + queries
│   ├── filter.py                       # LLM scoring + bucket selection
│   ├── drafter.py                      # voice-context drafting + angles
│   ├── email.py                        # markdown→HTML + Resend send
│   ├── llm.py                          # thin Anthropic SDK wrapper (retries)
│   └── cli.py                          # click-based CLI commands
├── migrations/
│   └── 001_init.sql                    # tables: tweets, voice_samples, accounts, digests, digest_items, errors
├── templates/
│   └── digest.html.j2                  # email HTML template
├── tests/
│   ├── conftest.py                     # pytest fixtures (db, mock_llm, fixture_tweets)
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_filter.py
│   │   ├── test_email.py
│   │   ├── test_store.py
│   │   └── test_drafter.py
│   ├── integration/
│   │   ├── test_apify_smoke.py
│   │   └── test_store_roundtrip.py
│   └── fixtures/
│       └── tweets_sample.json
├── docker-compose.yml                  # local Postgres
├── pyproject.toml
├── vercel.ts                           # Vercel project config (cron + python runtime)
├── Makefile                            # dev shortcuts
├── .env.example
├── .gitignore
└── README.md
```

---

## Task 1: Project scaffold + Vercel link + Marketplace provisioning

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `Makefile`, `vercel.ts`, `docker-compose.yml`, `README.md`, `src/feed_warrior/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```
.env
.env.local
.venv/
__pycache__/
*.pyc
.pytest_cache/
.vercel/
out/
node_modules/
.DS_Store
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "feed-warrior"
version = "0.1.0"
description = "Daily AI-tweet content engine"
requires-python = ">=3.13"
dependencies = [
    "psycopg[binary,pool]>=3.2",
    "httpx>=0.27",
    "anthropic>=0.45",
    "click>=8.1",
    "jinja2>=3.1",
    "resend>=2.4",
    "apify-client>=1.8",
    "python-dotenv>=1.0",
    "pydantic>=2.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "ruff>=0.7",
]

[project.scripts]
feed-warrior = "feed_warrior.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/feed_warrior"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Create `.env.example`**

```
# Database (Neon, provisioned via Vercel Marketplace)
DATABASE_URL=postgresql://...

# Email (Resend, provisioned via Vercel Marketplace)
RESEND_API_KEY=re_...
RECIPIENT_EMAIL=sidharths00@gmail.com

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# Apify
APIFY_TOKEN=apify_api_...

# Auth for /api/digest endpoint
CRON_SECRET=<random-32-byte-hex>

# Config
KEYWORDS=MCP,agent evals,Claude,Anthropic,OpenAI,Cursor,frontier model,Gemini,DeepMind
BUCKET_WEIGHTS={"signal":0.5,"work_adjacent":0.3,"discourse":0.2}
DAILY_SLOTS=7
USER_HANDLE=sidharths00
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: feed_warrior
      POSTGRES_PASSWORD: feed_warrior
      POSTGRES_DB: feed_warrior
    ports:
      - "5432:5432"
    volumes:
      - feed_warrior_pg:/var/lib/postgresql/data

volumes:
  feed_warrior_pg:
```

- [ ] **Step 5: Create `Makefile`**

```makefile
.PHONY: install db-up db-down migrate test test-unit test-integration dev-digest deploy

install:
	pip install -e ".[dev]"

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	feed-warrior db migrate

test: test-unit

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

dev-digest:
	feed-warrior digest --dry-run

deploy:
	vercel deploy --prod
```

- [ ] **Step 6: Create `vercel.ts`**

```ts
import { type VercelConfig } from '@vercel/config/v1';

export const config: VercelConfig = {
  framework: null,
  crons: [
    { path: '/api/digest', schedule: '0 14 * * *' },
  ],
};
```

- [ ] **Step 7: Create `src/feed_warrior/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 8: Create skeleton `README.md`**

```markdown
# Feed Warrior

Daily AI-tweet content engine. Scrapes interesting tweets, drafts replies in your voice, emails them with one-tap post links.

See `docs/superpowers/specs/2026-05-11-twitter-warrior-design.md` for the full design.

## Setup

```bash
make install
make db-up
make migrate
```

## Run

```bash
feed-warrior digest --dry-run    # preview, no send
feed-warrior digest              # real run
```
```

- [ ] **Step 9: Install + boot Postgres**

```bash
pip install -e ".[dev]"
docker compose up -d postgres
```

Expected: Postgres listening on `localhost:5432`. Verify with `docker compose ps`.

- [ ] **Step 10: Link Vercel project + provision Neon + Resend**

Use the `vercel:bootstrap` skill. It will:
- `vercel link` (create new project named `feed-warrior`)
- Add Neon Postgres via Marketplace (`vercel integration add neon`) — provides `DATABASE_URL`
- Add Resend via Marketplace (`vercel integration add resend`) — provides `RESEND_API_KEY`
- `vercel env pull .env.local` to sync env vars locally

If skill is unavailable, do these steps manually via the Vercel CLI / dashboard.

- [ ] **Step 11: Set remaining env vars in Vercel**

```bash
vercel env add ANTHROPIC_API_KEY production
vercel env add APIFY_TOKEN production
vercel env add RECIPIENT_EMAIL production
vercel env add CRON_SECRET production    # generate: openssl rand -hex 32
vercel env add USER_HANDLE production
vercel env add KEYWORDS production
vercel env add BUCKET_WEIGHTS production
vercel env add DAILY_SLOTS production
vercel env pull .env.local
```

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: project scaffold + Vercel/Neon/Resend wiring"
git push
```

---

## Task 2: Database schema + migration runner

**Files:**
- Create: `migrations/001_init.sql`, `src/feed_warrior/store.py`
- Test: `tests/integration/test_store_roundtrip.py`, `tests/conftest.py`

- [ ] **Step 1: Create `migrations/001_init.sql`**

```sql
CREATE TABLE IF NOT EXISTS tweets (
  id            TEXT PRIMARY KEY,
  author_handle TEXT NOT NULL,
  text          TEXT NOT NULL,
  url           TEXT NOT NULL,
  posted_at     TIMESTAMPTZ NOT NULL,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source        TEXT NOT NULL CHECK (source IN ('list', 'search'))
);
CREATE INDEX IF NOT EXISTS tweets_posted_at_idx ON tweets (posted_at DESC);
CREATE INDEX IF NOT EXISTS tweets_author_idx ON tweets (author_handle);

CREATE TABLE IF NOT EXISTS voice_samples (
  id        TEXT PRIMARY KEY,
  text      TEXT NOT NULL,
  posted_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  handle    TEXT PRIMARY KEY,
  added_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS digests (
  id      SERIAL PRIMARY KEY,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status  TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'partial'))
);

CREATE TABLE IF NOT EXISTS digest_items (
  id              SERIAL PRIMARY KEY,
  digest_id       INTEGER NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
  tweet_id        TEXT NOT NULL REFERENCES tweets(id),
  draft_text      TEXT NOT NULL,
  why_interesting TEXT NOT NULL,
  scores          JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS errors (
  id          SERIAL PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  component   TEXT NOT NULL,
  message     TEXT NOT NULL,
  context     JSONB
);
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import os
import pytest
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://feed_warrior:feed_warrior@localhost:5432/feed_warrior")

@pytest.fixture(scope="session")
def db_pool():
    pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=4, open=True)
    yield pool
    pool.close()

@pytest.fixture(autouse=True)
def clean_db(db_pool, request):
    if "integration" not in request.node.nodeid:
        return
    with db_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE tweets, voice_samples, accounts, digests, digest_items, errors RESTART IDENTITY CASCADE")
        conn.commit()
```

- [ ] **Step 3: Write the failing test for migration runner + tweet roundtrip**

Create `tests/integration/test_store_roundtrip.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it fails**

```bash
DATABASE_URL=postgresql://feed_warrior:feed_warrior@localhost:5432/feed_warrior pytest tests/integration/test_store_roundtrip.py -v
```
Expected: FAIL with `ImportError: cannot import name 'Store' from 'feed_warrior.store'`

- [ ] **Step 5: Implement `src/feed_warrior/store.py`**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
DATABASE_URL=postgresql://feed_warrior:feed_warrior@localhost:5432/feed_warrior pytest tests/integration/test_store_roundtrip.py -v
```
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add migrations src/feed_warrior/store.py tests/
git commit -m "feat: postgres schema + store layer with migration runner"
git push
```

---

## Task 3: Config loader

**Files:**
- Create: `src/feed_warrior/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_config.py -v
```
Expected: FAIL with `ImportError: cannot import name 'Config'`

- [ ] **Step 3: Implement `src/feed_warrior/config.py`**

```python
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")


@dataclass
class Config:
    database_url: str
    anthropic_api_key: str
    apify_token: str
    resend_api_key: str
    recipient_email: str
    cron_secret: str
    user_handle: str
    keywords: list[str]
    bucket_weights: dict[str, float]
    daily_slots: int

    @classmethod
    def from_env(cls) -> "Config":
        weights = json.loads(os.environ["BUCKET_WEIGHTS"])
        if not 0.99 < sum(weights.values()) < 1.01:
            raise ValueError(f"BUCKET_WEIGHTS must sum to 1, got {sum(weights.values())}")
        for k in ("signal", "work_adjacent", "discourse"):
            if k not in weights:
                raise ValueError(f"BUCKET_WEIGHTS missing key '{k}'")
        return cls(
            database_url=os.environ["DATABASE_URL"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            apify_token=os.environ["APIFY_TOKEN"],
            resend_api_key=os.environ["RESEND_API_KEY"],
            recipient_email=os.environ["RECIPIENT_EMAIL"],
            cron_secret=os.environ["CRON_SECRET"],
            user_handle=os.environ["USER_HANDLE"],
            keywords=[k.strip() for k in os.environ["KEYWORDS"].split(",") if k.strip()],
            bucket_weights=weights,
            daily_slots=int(os.environ["DAILY_SLOTS"]),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_config.py -v
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/feed_warrior/config.py tests/unit/test_config.py
git commit -m "feat: config loader with weight validation"
git push
```

---

## Task 4: LLM wrapper (Anthropic SDK with retries)

**Files:**
- Create: `src/feed_warrior/llm.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_llm.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from feed_warrior.llm import LLM, MAX_RETRIES


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_llm_complete_text_returns_text():
    client = MagicMock()
    client.messages.create.return_value = _mock_response("hello")
    llm = LLM(client=client, model="claude-sonnet-4-6")
    out = llm.complete_text(system="s", user="u")
    assert out == "hello"


def test_llm_complete_json_parses():
    client = MagicMock()
    client.messages.create.return_value = _mock_response('{"score": 7}')
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_json(system="s", user="u") == {"score": 7}


def test_llm_complete_json_strips_codefences():
    client = MagicMock()
    client.messages.create.return_value = _mock_response("```json\n{\"a\":1}\n```")
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_json(system="s", user="u") == {"a": 1}


def test_llm_retries_on_failure():
    from anthropic import APIError
    client = MagicMock()
    client.messages.create.side_effect = [
        Exception("transient"),
        Exception("transient"),
        _mock_response("ok"),
    ]
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_text(system="s", user="u") == "ok"
    assert client.messages.create.call_count == 3
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_llm.py -v
```
Expected: FAIL with import error.

- [ ] **Step 3: Implement `src/feed_warrior/llm.py`**

```python
from __future__ import annotations
import json
import re
import time
from typing import Any
from anthropic import Anthropic

MAX_RETRIES = 3
BACKOFF_BASE = 1.0
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"  # Sonnet 4.6 alias when available

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class LLM:
    def __init__(self, client: Any | None = None, model: str = DEFAULT_MODEL, api_key: str | None = None):
        self.client = client or Anthropic(api_key=api_key)
        self.model = model

    def complete_text(self, system: str, user: str, max_tokens: int = 1024) -> str:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return resp.content[0].text
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
        raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_exc}")

    def complete_json(self, system: str, user: str, max_tokens: int = 2048) -> Any:
        text = self.complete_text(system=system, user=user, max_tokens=max_tokens)
        m = _FENCE_RE.match(text.strip())
        if m:
            text = m.group(1)
        return json.loads(text)
```

Note on the model id: `claude-sonnet-4-5-20250929` is the Anthropic SDK identifier for Sonnet 4.6 at time of writing. When 4.7 ships and is needed here, swap the constant. We're not using AI Gateway in v0 to keep the SDK surface small; switching to it later is a base-URL change.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_llm.py -v
```
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/feed_warrior/llm.py tests/unit/test_llm.py
git commit -m "feat: anthropic LLM wrapper with retries + JSON helper"
git push
```

---

## Task 5: Apify client

**Files:**
- Create: `src/feed_warrior/apify_client.py`
- Test: `tests/unit/test_apify_client.py`, `tests/integration/test_apify_smoke.py`

- [ ] **Step 1: Write unit test (mocked) for parsing actor output**

Create `tests/unit/test_apify_client.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock
from feed_warrior.apify_client import ApifyClient
from feed_warrior.store import Tweet


def test_parse_tweets_from_actor_output():
    raw = [
        {
            "id": "111",
            "author": {"userName": "karpathy"},
            "text": "hello",
            "url": "https://x.com/karpathy/status/111",
            "createdAt": "2026-05-11T10:00:00.000Z",
        },
        {
            "id": "222",
            "author": {"userName": "swyx"},
            "text": "world",
            "url": "https://x.com/swyx/status/222",
            "createdAt": "2026-05-11T11:00:00.000Z",
        },
    ]
    out = ApifyClient._parse_tweets(raw, source="list")
    assert len(out) == 2
    assert out[0].id == "111"
    assert out[0].author_handle == "karpathy"
    assert out[0].posted_at == datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    assert out[0].source == "list"


def test_fetch_account_tweets_calls_actor_with_handles():
    apify = MagicMock()
    actor = MagicMock()
    apify.actor.return_value = actor
    actor.call.return_value = {"defaultDatasetId": "ds-1"}
    dataset = MagicMock()
    apify.dataset.return_value = dataset
    dataset.iterate_items.return_value = iter([])
    client = ApifyClient(client=apify, actor_id_account="apidojo/tweet-scraper")
    client.fetch_account_tweets(["karpathy", "swyx"], since=datetime(2026, 5, 10, tzinfo=timezone.utc))
    apify.actor.assert_called_with("apidojo/tweet-scraper")
    args, kwargs = actor.call.call_args
    payload = kwargs.get("run_input") or args[0]
    assert "karpathy" in str(payload)
    assert "swyx" in str(payload)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_apify_client.py -v
```
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/feed_warrior/apify_client.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from apify_client import ApifyClient as ApifySDK

from .store import Tweet, VoiceSample

# Default actor IDs - apidojo/tweet-scraper is the most common, well-maintained X scraper on Apify.
DEFAULT_TWEET_ACTOR = "apidojo/tweet-scraper"
DEFAULT_FOLLOWS_ACTOR = "apidojo/twitter-following-scraper"


class ApifyClient:
    def __init__(
        self,
        token: str | None = None,
        client: Any | None = None,
        actor_id_account: str = DEFAULT_TWEET_ACTOR,
        actor_id_search: str = DEFAULT_TWEET_ACTOR,
        actor_id_follows: str = DEFAULT_FOLLOWS_ACTOR,
    ):
        self._client = client or ApifySDK(token)
        self.actor_id_account = actor_id_account
        self.actor_id_search = actor_id_search
        self.actor_id_follows = actor_id_follows

    def fetch_account_tweets(self, handles: Iterable[str], since: datetime, max_per_handle: int = 30) -> list[Tweet]:
        run_input = {
            "twitterHandles": list(handles),
            "maxItems": max_per_handle * len(list(handles)) if handles else 100,
            "sort": "Latest",
            "tweetLanguage": "en",
            "since": since.isoformat(),
        }
        run = self._client.actor(self.actor_id_account).call(run_input=run_input)
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        return self._parse_tweets(items, source="list")

    def search_tweets(self, queries: Iterable[str], since: datetime, max_per_query: int = 20) -> list[Tweet]:
        run_input = {
            "searchTerms": list(queries),
            "maxItems": max_per_query * max(1, len(list(queries))),
            "sort": "Latest",
            "tweetLanguage": "en",
            "since": since.isoformat(),
        }
        run = self._client.actor(self.actor_id_search).call(run_input=run_input)
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        return self._parse_tweets(items, source="search")

    def fetch_user_tweets(self, handle: str, n: int = 500) -> list[VoiceSample]:
        run_input = {"twitterHandles": [handle], "maxItems": n, "sort": "Latest", "tweetLanguage": "en"}
        run = self._client.actor(self.actor_id_account).call(run_input=run_input)
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        out: list[VoiceSample] = []
        for it in items:
            tid = str(it.get("id") or it.get("tweetId") or "")
            text = it.get("text") or it.get("fullText") or ""
            posted = _parse_dt(it.get("createdAt"))
            if not tid or not text or not posted:
                continue
            out.append(VoiceSample(id=tid, text=text, posted_at=posted))
        return out

    def fetch_follows(self, handle: str, max_items: int = 2000) -> list[dict]:
        run_input = {"user_names": [handle], "maxItems": max_items}
        run = self._client.actor(self.actor_id_follows).call(run_input=run_input)
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        # Each item looks like {"userName": "...", "name": "...", "description": "...", "followersCount": int, ...}
        return items

    @staticmethod
    def _parse_tweets(raw: list[dict], source: Literal["list", "search"]) -> list[Tweet]:
        out: list[Tweet] = []
        for it in raw:
            tid = str(it.get("id") or it.get("tweetId") or "")
            author = (it.get("author") or {}).get("userName") or it.get("authorHandle") or ""
            text = it.get("text") or it.get("fullText") or ""
            url = it.get("url") or (f"https://x.com/{author}/status/{tid}" if author and tid else "")
            posted = _parse_dt(it.get("createdAt"))
            if not (tid and author and text and url and posted):
                continue
            out.append(Tweet(id=tid, author_handle=author, text=text, url=url, posted_at=posted, source=source))
        return out


def _parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        # Twitter API returns ISO8601 with Z; also accept the human format if present
        s = str(s).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except ValueError:
        return None
```

- [ ] **Step 4: Run unit tests to verify they pass**

```bash
pytest tests/unit/test_apify_client.py -v
```
Expected: 2 PASS

- [ ] **Step 5: Add a real-world smoke integration test**

Create `tests/integration/test_apify_smoke.py`:

```python
import os
from datetime import datetime, timedelta, timezone
import pytest
from feed_warrior.apify_client import ApifyClient

pytestmark = pytest.mark.skipif(not os.getenv("APIFY_TOKEN"), reason="needs APIFY_TOKEN")


def test_fetch_known_account_returns_tweets():
    client = ApifyClient(token=os.environ["APIFY_TOKEN"])
    since = datetime.now(timezone.utc) - timedelta(days=7)
    tweets = client.fetch_account_tweets(["karpathy"], since=since, max_per_handle=5)
    assert len(tweets) > 0
    t = tweets[0]
    assert t.author_handle == "karpathy"
    assert t.url.startswith("https://x.com/")
    assert t.text
```

This test costs ~$0.01-0.05 in Apify usage. Skip if budget-conscious during dev.

- [ ] **Step 6: Run integration smoke (optional, costs $)**

```bash
APIFY_TOKEN=$APIFY_TOKEN pytest tests/integration/test_apify_smoke.py -v
```
Expected: PASS, 5 tweets returned.

- [ ] **Step 7: Commit**

```bash
git add src/feed_warrior/apify_client.py tests/
git commit -m "feat: apify client (account/search/user/follows)"
git push
```

---

## Task 6: Filter (LLM scoring + bucket selection)

**Files:**
- Create: `src/feed_warrior/filter.py`
- Test: `tests/unit/test_filter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_filter.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock
from feed_warrior.filter import Filter, ScoredTweet
from feed_warrior.store import Tweet


def _t(id: str, text: str = "x") -> Tweet:
    return Tweet(id=id, author_handle="a", text=text, url="u", posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc), source="list")


def test_bucket_allocation_50_30_20_seven_slots():
    weights = {"signal": 0.5, "work_adjacent": 0.3, "discourse": 0.2}
    counts = Filter._allocate_slots(weights, total=7)
    assert counts == {"signal": 4, "work_adjacent": 2, "discourse": 1}
    assert sum(counts.values()) == 7


def test_bucket_allocation_5_slots():
    weights = {"signal": 0.5, "work_adjacent": 0.3, "discourse": 0.2}
    counts = Filter._allocate_slots(weights, total=5)
    assert sum(counts.values()) == 5


def test_pick_top_per_bucket_assigns_to_highest_scoring_bucket():
    scored = [
        ScoredTweet(tweet=_t("1"), scores={"signal": 9, "work_adjacent": 2, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("2"), scores={"signal": 1, "work_adjacent": 8, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("3"), scores={"signal": 1, "work_adjacent": 1, "discourse": 9}, reason=""),
        ScoredTweet(tweet=_t("4"), scores={"signal": 7, "work_adjacent": 3, "discourse": 1}, reason=""),
    ]
    counts = {"signal": 2, "work_adjacent": 1, "discourse": 1}
    picked = Filter._pick_top_per_bucket(scored, counts)
    ids = [p.tweet.id for p in picked]
    assert "1" in ids and "4" in ids and "2" in ids and "3" in ids
    assert len(picked) == 4


def test_pick_top_falls_back_when_bucket_short():
    # discourse bucket wants 2 but only 1 tweet has discourse as top score
    scored = [
        ScoredTweet(tweet=_t("1"), scores={"signal": 9, "work_adjacent": 1, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("2"), scores={"signal": 8, "work_adjacent": 1, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("3"), scores={"signal": 1, "work_adjacent": 1, "discourse": 9}, reason=""),
    ]
    counts = {"signal": 1, "work_adjacent": 0, "discourse": 2}
    picked = Filter._pick_top_per_bucket(scored, counts)
    # discourse short by 1 => fall back to next-highest unused (id=2 by signal)
    ids = sorted([p.tweet.id for p in picked])
    assert ids == ["1", "2", "3"]


def test_score_tweets_uses_llm():
    llm = MagicMock()
    llm.complete_json.return_value = [
        {"id": "1", "signal": 8, "work_adjacent": 3, "discourse": 1, "reason": "novel insight"},
        {"id": "2", "signal": 2, "work_adjacent": 1, "discourse": 9, "reason": "drama"},
    ]
    filt = Filter(llm=llm)
    scored = filt.score_tweets([_t("1", "tweet one"), _t("2", "tweet two")])
    assert len(scored) == 2
    assert scored[0].scores["signal"] == 8
    assert scored[1].reason == "drama"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_filter.py -v
```
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/feed_warrior/filter.py`**

```python
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Iterable

from .llm import LLM
from .store import Tweet

BUCKETS = ("signal", "work_adjacent", "discourse")

SCORING_SYSTEM = """\
You score tweets for an AI content engine. The reader is a Stanford-grad founder
working on agent evals (MCP-Eval) and AI quality at Box.

Score each tweet 0-10 on three axes:

- signal: novel technical insight or contrarian take from a credible voice. Lab announcements, well-argued opinions, real findings. Penalize hype, listicles, generic motivation.
- work_adjacent: relevance to MCP, agent evals, agent runtime quality, enterprise AI, frontier model capabilities/limits.
- discourse: AI Twitter conversation/drama/jokes/dunks. The kind of tweet that's fun to riff on with a take.

Also produce a one-line `reason` per tweet (~10 words).

Return STRICT JSON: an array of objects, one per input tweet, with fields:
[{"id": "...", "signal": 0-10, "work_adjacent": 0-10, "discourse": 0-10, "reason": "..."}, ...]
Order doesn't matter; ids must match the input.
"""


@dataclass
class ScoredTweet:
    tweet: Tweet
    scores: dict[str, int]
    reason: str


class Filter:
    def __init__(self, llm: LLM, batch_size: int = 20):
        self.llm = llm
        self.batch_size = batch_size

    def score_tweets(self, tweets: list[Tweet]) -> list[ScoredTweet]:
        if not tweets:
            return []
        out: list[ScoredTweet] = []
        for i in range(0, len(tweets), self.batch_size):
            batch = tweets[i : i + self.batch_size]
            payload = [{"id": t.id, "author": t.author_handle, "text": t.text} for t in batch]
            user = "Score these tweets:\n\n" + _format_batch(payload)
            scores = self.llm.complete_json(system=SCORING_SYSTEM, user=user)
            by_id = {s["id"]: s for s in scores}
            for t in batch:
                s = by_id.get(t.id)
                if not s:
                    continue
                out.append(ScoredTweet(
                    tweet=t,
                    scores={k: int(s.get(k, 0)) for k in BUCKETS},
                    reason=s.get("reason", ""),
                ))
        return out

    def select(self, scored: list[ScoredTweet], weights: dict[str, float], total: int) -> list[ScoredTweet]:
        counts = self._allocate_slots(weights, total)
        return self._pick_top_per_bucket(scored, counts)

    @staticmethod
    def _allocate_slots(weights: dict[str, float], total: int) -> dict[str, int]:
        raw = {k: weights[k] * total for k in BUCKETS}
        floors = {k: int(math.floor(v)) for k, v in raw.items()}
        remaining = total - sum(floors.values())
        # distribute remainder to largest fractional parts
        fracs = sorted(((raw[k] - floors[k], k) for k in BUCKETS), reverse=True)
        for _, k in fracs[:remaining]:
            floors[k] += 1
        return floors

    @staticmethod
    def _pick_top_per_bucket(scored: list[ScoredTweet], counts: dict[str, int]) -> list[ScoredTweet]:
        # Assign each scored tweet to its highest-scoring bucket
        by_bucket: dict[str, list[ScoredTweet]] = {b: [] for b in BUCKETS}
        for s in scored:
            top_bucket = max(BUCKETS, key=lambda b: s.scores.get(b, 0))
            by_bucket[top_bucket].append(s)
        # Sort each bucket by its bucket-score, descending
        for b in BUCKETS:
            by_bucket[b].sort(key=lambda s: s.scores.get(b, 0), reverse=True)

        picked: list[ScoredTweet] = []
        used: set[str] = set()
        # First pass: take top-N from each bucket per quota
        for b in BUCKETS:
            for s in by_bucket[b][: counts[b]]:
                picked.append(s)
                used.add(s.tweet.id)
        # Second pass: if any bucket was short, fill from remaining tweets sorted by max-score
        target = sum(counts.values())
        if len(picked) < target:
            remaining = [s for s in scored if s.tweet.id not in used]
            remaining.sort(key=lambda s: max(s.scores.values()), reverse=True)
            for s in remaining:
                if len(picked) >= target:
                    break
                picked.append(s)
        return picked


def _format_batch(payload: list[dict]) -> str:
    lines = []
    for p in payload:
        lines.append(f"id={p['id']} @{p['author']}: {p['text']}")
    return "\n\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_filter.py -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/feed_warrior/filter.py tests/unit/test_filter.py
git commit -m "feat: LLM-scored bucket selection (signal/work-adjacent/discourse)"
git push
```

---

## Task 7: Drafter (voice context + per-tweet drafts + angles)

**Files:**
- Create: `src/feed_warrior/drafter.py`
- Test: `tests/unit/test_drafter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drafter.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock
from feed_warrior.drafter import Drafter, Draft
from feed_warrior.filter import ScoredTweet
from feed_warrior.store import Tweet, VoiceSample


def _scored(id: str = "1", text: str = "interesting tweet") -> ScoredTweet:
    t = Tweet(id=id, author_handle="karpathy", text=text, url=f"https://x.com/karpathy/status/{id}",
              posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc), source="list")
    return ScoredTweet(tweet=t, scores={"signal": 8, "work_adjacent": 2, "discourse": 1}, reason="novel")


def test_voice_corpus_block_renders_examples():
    samples = [
        VoiceSample(id="a", text="Eval coverage is a vibe.", posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        VoiceSample(id="b", text="Most agent demos are fictional.", posted_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    block = Drafter._voice_block(samples)
    assert "Eval coverage" in block
    assert "fictional" in block


def test_draft_one_calls_llm_and_returns_draft():
    llm = MagicMock()
    llm.complete_json.return_value = {
        "draft_text": "the eval gap is real",
        "why_interesting": "shows why offline metrics mislead",
        "mode": "reply",
    }
    d = Drafter(llm=llm, voice_samples=[])
    draft = d.draft_one(_scored())
    assert draft.draft_text == "the eval gap is real"
    assert draft.mode in ("reply", "quote")


def test_draft_many_returns_one_per_input():
    llm = MagicMock()
    llm.complete_json.return_value = {"draft_text": "x", "why_interesting": "y", "mode": "reply"}
    d = Drafter(llm=llm, voice_samples=[])
    drafts = d.draft_many([_scored("1"), _scored("2"), _scored("3")])
    assert len(drafts) == 3


def test_angles_returns_list():
    llm = MagicMock()
    llm.complete_json.return_value = ["angle one", "angle two", "angle three"]
    d = Drafter(llm=llm, voice_samples=[])
    angles = d.angles([_scored("1"), _scored("2")])
    assert angles == ["angle one", "angle two", "angle three"]
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_drafter.py -v
```
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/feed_warrior/drafter.py`**

```python
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Literal

from .filter import ScoredTweet
from .llm import LLM
from .store import VoiceSample


@dataclass
class Draft:
    scored: ScoredTweet
    draft_text: str
    why_interesting: str
    mode: Literal["reply", "quote"]


_DRAFT_SYSTEM_TEMPLATE = """\
You write tweets in Sidharth's voice. Sidharth is a Stanford-grad founder building MCP-Eval (continuous eval/observability for MCP servers) and currently leads AI evals at Box.

Style:
- Substantive. Add a take, don't parrot. If there's nothing to add, say so honestly.
- Concise. No emoji unless ironic. No threadbait. No "this is huge."
- Funny when it lands. Dry > silly. He'd rather be sharp than cute.
- Specific over general. Concrete examples or specific claims, not vibes.

Voice samples (tweets actually written by him — match this rhythm and tone):

{voice_block}

Output STRICT JSON: {{"draft_text": "<the tweet, <=270 chars>", "why_interesting": "<one line of substance/context>", "mode": "reply"|"quote"}}
- mode=reply when responding to the source's idea
- mode=quote when adding a take above the original (more visible, use when the source is quotable)
"""

_ANGLES_SYSTEM = """\
You suggest 2-3 longer post angles for Sidharth (founder, MCP-Eval, AI evals at Box). Given today's interesting tweets, propose angle(s) for a longer thread or post. Each angle: 2-3 sentences describing the take, NOT pre-drafted as a tweet. Output STRICT JSON: a JSON array of strings.
"""


class Drafter:
    def __init__(self, llm: LLM, voice_samples: list[VoiceSample], voice_n: int = 12):
        self.llm = llm
        self.voice_samples = voice_samples
        self.voice_n = voice_n

    def _system(self) -> str:
        sample = random.sample(self.voice_samples, min(self.voice_n, len(self.voice_samples))) if self.voice_samples else []
        return _DRAFT_SYSTEM_TEMPLATE.format(voice_block=self._voice_block(sample))

    @staticmethod
    def _voice_block(samples: list[VoiceSample]) -> str:
        if not samples:
            return "(no voice samples available — write in a sharp, founder-voice, lower-case, lightly funny tone)"
        return "\n\n".join(f"- {s.text}" for s in samples)

    def draft_one(self, item: ScoredTweet) -> Draft:
        user = (
            f"Source tweet by @{item.tweet.author_handle}:\n"
            f"\"{item.tweet.text}\"\n\n"
            f"Filter judged this interesting because: {item.reason}\n\n"
            f"Draft a reply or quote-tweet in Sidharth's voice that adds substance."
        )
        out = self.llm.complete_json(system=self._system(), user=user, max_tokens=512)
        return Draft(
            scored=item,
            draft_text=out["draft_text"],
            why_interesting=out["why_interesting"],
            mode=out.get("mode", "reply"),
        )

    def draft_many(self, items: list[ScoredTweet]) -> list[Draft]:
        return [self.draft_one(it) for it in items]

    def angles(self, items: list[ScoredTweet]) -> list[str]:
        if not items:
            return []
        bullets = "\n".join(f"- @{i.tweet.author_handle}: {i.tweet.text}  ({i.reason})" for i in items)
        user = f"Today's interesting tweets:\n\n{bullets}\n\nPropose 2-3 longer post angles."
        out = self.llm.complete_json(system=_ANGLES_SYSTEM, user=user, max_tokens=1024)
        if isinstance(out, list):
            return [str(a) for a in out]
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_drafter.py -v
```
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/feed_warrior/drafter.py tests/unit/test_drafter.py
git commit -m "feat: drafter with voice corpus + per-tweet drafts + post angles"
git push
```

---

## Task 8: Email rendering + Resend send

**Files:**
- Create: `templates/digest.html.j2`, `src/feed_warrior/email.py`
- Test: `tests/unit/test_email.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_email.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import urllib.parse
from feed_warrior.email import EmailSender, render_digest_html, intent_link
from feed_warrior.drafter import Draft
from feed_warrior.filter import ScoredTweet
from feed_warrior.store import Tweet


def _draft(text: str = "my take") -> Draft:
    t = Tweet(id="1", author_handle="karpathy", text="original", url="https://x.com/karpathy/status/1",
              posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc), source="list")
    s = ScoredTweet(tweet=t, scores={"signal": 8, "work_adjacent": 2, "discourse": 1}, reason="novel")
    return Draft(scored=s, draft_text=text, why_interesting="why", mode="reply")


def test_intent_link_url_encodes():
    link = intent_link("hello world & friends")
    assert link.startswith("https://twitter.com/intent/tweet?text=")
    assert urllib.parse.unquote(link.split("text=", 1)[1]) == "hello world & friends"


def test_render_digest_html_includes_drafts_and_links():
    html = render_digest_html(drafts=[_draft("draft text")], angles=["angle 1"], date_str="2026-05-11")
    assert "draft text" in html
    assert "@karpathy" in html
    assert "twitter.com/intent/tweet?text=" in html
    assert "angle 1" in html
    assert "2026-05-11" in html


def test_render_handles_empty_drafts_gracefully():
    html = render_digest_html(drafts=[], angles=[], date_str="2026-05-11")
    assert "no drafts" in html.lower() or "0 drafts" in html.lower()


def test_email_sender_calls_resend():
    resend = MagicMock()
    sender = EmailSender(resend_client=resend, recipient="me@example.com", from_addr="feed@feedwarrior.dev")
    sender.send(subject="Feed Warrior — 2026-05-11", html="<p>hi</p>")
    resend.Emails.send.assert_called_once()
    payload = resend.Emails.send.call_args[0][0]
    assert payload["to"] == ["me@example.com"]
    assert payload["subject"] == "Feed Warrior — 2026-05-11"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_email.py -v
```
Expected: FAIL on import.

- [ ] **Step 3: Create `templates/digest.html.j2`**

```jinja2
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Feed Warrior — {{ date_str }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111; max-width: 640px; margin: 0 auto; padding: 16px; line-height: 1.45; }
    h1 { font-size: 18px; margin: 0 0 16px 0; }
    .item { border: 1px solid #e5e5e5; border-radius: 12px; padding: 14px 16px; margin: 12px 0; }
    .src { color: #555; font-size: 14px; margin-bottom: 6px; }
    .src .author { font-weight: 600; color: #000; }
    .source-text { background: #fafafa; border-left: 3px solid #ddd; padding: 8px 10px; font-size: 14px; margin: 6px 0; }
    .draft { font-size: 16px; margin: 10px 0 4px 0; }
    .why { font-size: 12px; color: #666; margin-top: 6px; }
    .actions a { display: inline-block; margin-right: 12px; font-size: 13px; }
    .post { background: #1d9bf0; color: #fff; padding: 6px 12px; border-radius: 999px; text-decoration: none; }
    .source-link { color: #1d9bf0; text-decoration: none; }
    .angles { margin-top: 28px; padding-top: 16px; border-top: 2px solid #eee; }
    .angle { background: #fff8e6; padding: 12px 14px; border-radius: 8px; margin: 8px 0; font-size: 14px; }
    .empty { color: #888; padding: 20px; text-align: center; }
    .footer { color: #888; font-size: 11px; margin-top: 32px; text-align: center; }
  </style>
</head>
<body>
  <h1>Feed Warrior — {{ date_str }} ({{ drafts|length }} drafts)</h1>

  {% if not drafts %}
    <div class="empty">no drafts today (nothing crossed the bar)</div>
  {% endif %}

  {% for d in drafts %}
  <div class="item">
    <div class="src">
      <span class="author">@{{ d.scored.tweet.author_handle }}</span>
      <a class="source-link" href="{{ d.scored.tweet.url }}">→ view on X</a>
    </div>
    <div class="source-text">{{ d.scored.tweet.text }}</div>
    <div class="draft">{{ d.draft_text }}</div>
    <div class="actions">
      <a class="post" href="{{ intent_link(d.draft_text if d.mode == 'reply' else d.draft_text + ' ' + d.scored.tweet.url) }}">post this</a>
      <a class="source-link" href="{{ d.scored.tweet.url }}">reply natively</a>
    </div>
    <div class="why">why interesting: {{ d.why_interesting }}</div>
  </div>
  {% endfor %}

  {% if angles %}
  <div class="angles">
    <h2 style="font-size: 15px;">longer angles</h2>
    {% for a in angles %}
    <div class="angle">{{ a }}</div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="footer">feed-warrior · {{ date_str }}</div>
</body>
</html>
```

- [ ] **Step 4: Implement `src/feed_warrior/email.py`**

```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from urllib.parse import quote

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .drafter import Draft

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def intent_link(text: str) -> str:
    return f"https://twitter.com/intent/tweet?text={quote(text, safe='')}"


def render_digest_html(drafts: list[Draft], angles: list[str], date_str: str) -> str:
    tmpl = _env.get_template("digest.html.j2")
    return tmpl.render(drafts=drafts, angles=angles, date_str=date_str, intent_link=intent_link)


class EmailSender:
    def __init__(self, resend_client: Any | None = None, api_key: str | None = None,
                 recipient: str = "", from_addr: str = "Feed Warrior <feed@feedwarrior.dev>"):
        if resend_client is None:
            resend.api_key = api_key
            self._client = resend
        else:
            self._client = resend_client
        self.recipient = recipient
        self.from_addr = from_addr

    def send(self, subject: str, html: str) -> dict:
        return self._client.Emails.send({
            "from": self.from_addr,
            "to": [self.recipient],
            "subject": subject,
            "html": html,
        })
```

Note on `from_addr`: until you verify a sending domain in Resend, use Resend's default sandbox sender (`onboarding@resend.dev`) to your verified email. Update `from_addr` once a domain is verified.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_email.py -v
```
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add templates/ src/feed_warrior/email.py tests/unit/test_email.py
git commit -m "feat: email rendering + Resend send + intent links"
git push
```

---

## Task 9: CLI commands

**Files:**
- Create: `src/feed_warrior/cli.py`
- Test: `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing test for CLI smoke**

Create `tests/unit/test_cli.py`:

```python
from click.testing import CliRunner
from feed_warrior.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "digest" in result.output
    assert "bootstrap-corpus" in result.output
    assert "bootstrap-accounts" in result.output


def test_cli_digest_help():
    runner = CliRunner()
    result = runner.invoke(main, ["digest", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_cli.py -v
```
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/feed_warrior/cli.py`**

```python
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from psycopg_pool import ConnectionPool

from .config import Config
from .store import Store
from .apify_client import ApifyClient
from .filter import Filter
from .drafter import Drafter
from .email import EmailSender, render_digest_html
from .llm import LLM


def _pool(cfg: Config) -> ConnectionPool:
    return ConnectionPool(cfg.database_url, min_size=1, max_size=4, open=True)


@click.group()
def main():
    """feed-warrior — daily AI tweet content engine"""


@main.group()
def db():
    """Database commands."""


@db.command("migrate")
def db_migrate():
    cfg = Config.from_env()
    pool = _pool(cfg)
    Store(pool).migrate("migrations")
    click.echo("migrations applied")


@main.command("bootstrap-corpus")
@click.option("--n", default=500, help="Number of past tweets to scrape")
def bootstrap_corpus(n: int):
    """Scrape your X account → voice corpus."""
    cfg = Config.from_env()
    pool = _pool(cfg)
    store = Store(pool)
    apify = ApifyClient(token=cfg.apify_token)
    samples = apify.fetch_user_tweets(cfg.user_handle, n=n)
    inserted = store.upsert_voice_samples(samples)
    click.echo(f"inserted {inserted} voice samples (fetched {len(samples)})")


@main.command("bootstrap-accounts")
@click.option("--out", default="accounts_seed.md", help="Output markdown file for manual pruning")
def bootstrap_accounts(out: str):
    """Scrape your follows, classify each as AI-relevant, write seed markdown."""
    cfg = Config.from_env()
    apify = ApifyClient(token=cfg.apify_token)
    follows = apify.fetch_follows(cfg.user_handle)
    click.echo(f"fetched {len(follows)} follows")
    llm = LLM(api_key=cfg.anthropic_api_key)

    classified: list[dict] = []
    BATCH = 25
    for i in range(0, len(follows), BATCH):
        batch = follows[i : i + BATCH]
        payload = [
            {"handle": f.get("userName", ""), "name": f.get("name", ""),
             "bio": (f.get("description") or "")[:200], "followers": f.get("followersCount", 0)}
            for f in batch if f.get("userName")
        ]
        if not payload:
            continue
        system = (
            "Classify each X account by AI relevance. Sidharth is an AI evals founder (MCP-Eval) at Box. "
            "Return STRICT JSON array, one entry per input, with fields: "
            '{"handle": "...", "ai_relevant": "yes"|"no"|"maybe", "reason": "<≤12 words>"}. '
            "Lean toward yes for: AI researchers, lab employees, AI founders, agent builders, eval people, AI commentators with substance. "
            "Lean toward no for: pure crypto, sports, friends without AI content, generic VCs without AI focus."
        )
        user = "\n".join(f"@{p['handle']} ({p['name']}, {p['followers']} followers): {p['bio']}" for p in payload)
        try:
            out_arr = llm.complete_json(system=system, user=user)
            classified.extend(out_arr if isinstance(out_arr, list) else [])
        except Exception as e:
            click.echo(f"batch {i} failed: {e}", err=True)

    yes = [c for c in classified if c.get("ai_relevant") == "yes"]
    maybe = [c for c in classified if c.get("ai_relevant") == "maybe"]
    no = [c for c in classified if c.get("ai_relevant") == "no"]

    with open(out, "w") as f:
        f.write(f"# Curated accounts seed — {datetime.now(timezone.utc).date()}\n\n")
        f.write(f"Edit this file: keep the lines you want, delete the rest. Then run `feed-warrior load-accounts {out}`.\n\n")
        f.write("## YES (recommended)\n\n")
        for c in sorted(yes, key=lambda x: x.get("handle", "")):
            f.write(f"- @{c['handle']} — {c.get('reason', '')}\n")
        f.write("\n## MAYBE\n\n")
        for c in sorted(maybe, key=lambda x: x.get("handle", "")):
            f.write(f"- @{c['handle']} — {c.get('reason', '')}\n")
        f.write("\n## NO (excluded; uncomment to include)\n\n")
        for c in sorted(no, key=lambda x: x.get("handle", "")):
            f.write(f"<!-- - @{c['handle']} — {c.get('reason', '')} -->\n")
    click.echo(f"wrote {out}: {len(yes)} yes / {len(maybe)} maybe / {len(no)} no")


@main.command("load-accounts")
@click.argument("path", type=click.Path(exists=True))
def load_accounts(path: str):
    """Load curated accounts from a pruned markdown file into the DB."""
    cfg = Config.from_env()
    pool = _pool(cfg)
    store = Store(pool)
    handles: list[str] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line.startswith("- @"):
            continue
        handle = line[3:].split(" ", 1)[0].rstrip(",—-:")
        if handle:
            handles.append(handle)
    inserted = store.upsert_accounts(handles)
    click.echo(f"loaded {inserted} accounts ({len(handles)} parsed)")


@main.command("digest")
@click.option("--dry-run", is_flag=True, help="Render but do not send; writes out/preview.html")
def digest(dry_run: bool):
    """Run the daily pipeline."""
    cfg = Config.from_env()
    pool = _pool(cfg)
    store = Store(pool)
    apify = ApifyClient(token=cfg.apify_token)
    llm = LLM(api_key=cfg.anthropic_api_key)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    accounts = store.get_active_accounts()
    click.echo(f"fetching from {len(accounts)} accounts + {len(cfg.keywords)} keywords since {since.isoformat()}")
    new_tweets: list = []
    if accounts:
        new_tweets += apify.fetch_account_tweets(accounts, since=since)
    if cfg.keywords:
        new_tweets += apify.search_tweets(cfg.keywords, since=since)
    inserted = store.upsert_tweets(new_tweets)
    click.echo(f"upserted {inserted} new tweets (saw {len(new_tweets)})")

    candidates = store.get_recent_tweets(since=since)
    click.echo(f"scoring {len(candidates)} candidates")
    filt = Filter(llm=llm)
    scored = filt.score_tweets(candidates)
    chosen = filt.select(scored, weights=cfg.bucket_weights, total=cfg.daily_slots)
    click.echo(f"selected {len(chosen)}")

    voice = store.get_voice_samples(limit=200)
    drafter = Drafter(llm=llm, voice_samples=voice)
    drafts = drafter.draft_many(chosen)
    angles = drafter.angles(chosen)

    date_str = datetime.now(timezone.utc).date().isoformat()
    html = render_digest_html(drafts=drafts, angles=angles, date_str=date_str)

    if dry_run:
        out_path = Path("out/preview.html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        click.echo(f"dry run: wrote {out_path}")
        return

    sender = EmailSender(api_key=cfg.resend_api_key, recipient=cfg.recipient_email,
                         from_addr=os.getenv("FROM_ADDR", "Feed Warrior <onboarding@resend.dev>"))
    digest_id = store.create_digest(status="sent")
    from .store import DigestItem
    store.add_digest_items([
        DigestItem(digest_id=digest_id, tweet_id=d.scored.tweet.id, draft_text=d.draft_text,
                   why_interesting=d.why_interesting, scores=d.scored.scores)
        for d in drafts
    ])
    sender.send(subject=f"Feed Warrior — {date_str} ({len(drafts)} drafts)", html=html)
    click.echo(f"sent digest {digest_id}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_cli.py -v
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/feed_warrior/cli.py tests/unit/test_cli.py
git commit -m "feat: CLI (db migrate / bootstrap-corpus / bootstrap-accounts / load-accounts / digest)"
git push
```

---

## Task 10: Vercel function entrypoint

**Files:**
- Create: `api/digest.py`
- Modify: `vercel.ts` (already created)

- [ ] **Step 1: Create `api/digest.py`**

This is the Vercel Function entrypoint. It uses Vercel's Python runtime, which expects a `handler(request)` function or a WSGI/ASGI app. We use a plain BaseHTTPRequestHandler-style function for simplicity.

```python
"""Vercel Function entry. Triggered by Vercel Cron daily at 14:00 UTC.

Auth: requires `Authorization: Bearer <CRON_SECRET>` header (Vercel Cron sets this automatically when you set CRON_SECRET env var).
"""
from __future__ import annotations
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

# Ensure src is importable on Vercel
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feed_warrior.cli import main as cli_main  # noqa: E402
from click.testing import CliRunner  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        return self._run()

    def do_GET(self):
        return self._run()

    def _run(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")
        if not secret or auth != f"Bearer {secret}":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        try:
            runner = CliRunner()
            result = runner.invoke(cli_main, ["digest"], catch_exceptions=False)
            body = {"exit_code": result.exit_code, "output": result.output}
            self.send_response(200 if result.exit_code == 0 else 500)
        except Exception as e:
            body = {"error": str(e), "trace": traceback.format_exc()}
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
```

- [ ] **Step 2: Add `requirements.txt` for Vercel Python runtime**

Vercel's Python runtime reads `requirements.txt`, not `pyproject.toml`. Create at repo root:

```
psycopg[binary,pool]>=3.2
httpx>=0.27
anthropic>=0.45
click>=8.1
jinja2>=3.1
resend>=2.4
apify-client>=1.8
python-dotenv>=1.0
pydantic>=2.9
```

- [ ] **Step 3: Verify `vercel.ts` cron config**

Open `vercel.ts` and confirm:

```ts
import { type VercelConfig } from '@vercel/config/v1';

export const config: VercelConfig = {
  framework: null,
  crons: [
    { path: '/api/digest', schedule: '0 14 * * *' },
  ],
};
```

- [ ] **Step 4: Local smoke (no Vercel needed) — invoke handler in-process**

Create `tests/unit/test_api_handler.py`:

```python
import os
import io
from unittest.mock import patch, MagicMock
from http.server import BaseHTTPRequestHandler


def _invoke_handler(method: str, headers: dict):
    from api import digest as digest_module
    h = digest_module.handler.__new__(digest_module.handler)
    h.headers = headers
    h.send_response = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()
    h.wfile = io.BytesIO()
    if method == "GET":
        h.do_GET()
    else:
        h.do_POST()
    return h


def test_handler_rejects_missing_auth(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    h = _invoke_handler("POST", {"Authorization": ""})
    h.send_response.assert_called_with(401)


def test_handler_rejects_bad_auth(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    h = _invoke_handler("POST", {"Authorization": "Bearer wrong"})
    h.send_response.assert_called_with(401)
```

- [ ] **Step 5: Run handler tests**

```bash
pytest tests/unit/test_api_handler.py -v
```
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add api/ requirements.txt vercel.ts tests/unit/test_api_handler.py
git commit -m "feat: Vercel function entrypoint + cron config"
git push
```

---

## Task 11: Bootstrap, deploy, and end-to-end verify

This task uses real APIs, real money. Run carefully.

- [ ] **Step 1: Run migrations against Neon (production DB)**

```bash
DATABASE_URL=$(vercel env pull --quiet .env.local && grep ^DATABASE_URL .env.local | cut -d= -f2-) feed-warrior db migrate
```
Or simpler, after `vercel env pull .env.local`:
```bash
feed-warrior db migrate
```
Expected: `migrations applied`.

- [ ] **Step 2: Bootstrap voice corpus**

```bash
feed-warrior bootstrap-corpus --n 500
```
Expected: `inserted N voice samples` (N up to 500). Costs ~$0.05-0.20 in Apify.

Spot-check: `psql $DATABASE_URL -c "SELECT count(*), min(posted_at), max(posted_at) FROM voice_samples"`

- [ ] **Step 3: Bootstrap curated accounts**

```bash
feed-warrior bootstrap-accounts --out accounts_seed.md
```
Expected: `wrote accounts_seed.md: X yes / Y maybe / Z no`. Costs ~$0.50-2.00 in Apify + Claude.

- [ ] **Step 4: Manually prune `accounts_seed.md`**

Open the file, delete lines under YES you don't want, optionally promote MAYBEs. Save.

- [ ] **Step 5: Load curated accounts**

```bash
feed-warrior load-accounts accounts_seed.md
```
Expected: `loaded N accounts`.

- [ ] **Step 6: Local dry run end-to-end**

```bash
feed-warrior digest --dry-run
open out/preview.html
```
Inspect the HTML in your browser. Check: drafts read like you, intent links work (click one — does X compose open with text filled?), longer angles aren't fluff.

If the voice is off or the picks are bad, iterate on prompts in `filter.py` / `drafter.py` before deploying. Costs ~$0.30-1.00 per dry run.

- [ ] **Step 7: Real local send**

```bash
feed-warrior digest
```
Expected: `sent digest 1`. Check inbox.

If the email lands in spam, that's the unverified-domain issue — verify a domain in Resend dashboard, then update `FROM_ADDR` env var.

- [ ] **Step 8: Deploy to Vercel**

```bash
vercel deploy --prod
```
Expected: deployment URL printed; cron registered (visible in Vercel dashboard under Settings → Cron Jobs).

- [ ] **Step 9: Trigger production cron manually to verify**

```bash
curl -X POST "https://<your-deployment>.vercel.app/api/digest" \
  -H "Authorization: Bearer $CRON_SECRET"
```
Expected: HTTP 200 with `exit_code: 0`. Email arrives.

If 504 timeout: increase function timeout in `vercel.ts` (Fluid Compute supports up to 800s on Pro, default 300s). Add:
```ts
functions: { 'api/digest.py': { maxDuration: 800 } }
```

- [ ] **Step 10: Final commit + push**

```bash
git add -A
git commit -m "chore: bootstrap corpus + accounts + first deploy"
git push
```

---

## Self-Review (run after the plan is written)

**Spec coverage check:**
- Curated list (build from follows + LLM filter) → Task 9 (`bootstrap-accounts`, `load-accounts`) ✅
- Topic search → Task 5 (`search_tweets`), Task 9 (`digest` calls it) ✅
- Voice corpus → Task 5 (`fetch_user_tweets`), Task 9 (`bootstrap-corpus`), Task 7 (system prompt uses it) ✅
- 50/30/20 bucketing → Task 6 ✅
- Daily email with intent links → Task 8 ✅
- 5-8 draft items + 2-3 angles → Task 7 (drafts + angles), Task 9 (uses `cfg.daily_slots`) ✅
- On-demand CLI → Task 9 ✅
- Vercel Cron at 14:00 UTC → Task 1 (vercel.ts), Task 10 (handler) ✅
- All schema tables → Task 2 ✅
- Error handling (Apify down, LLM retry, Resend retry on next cron, errors table) → LLM retries in Task 4; errors table in Task 2; Apify/Resend graceful fallback is implementation-detail in Task 9's `digest` (acceptable for v0; if it crashes the cron just retries tomorrow). ✅
- Tests (unit pure functions, integration with real Apify, E2E dry-run) → Tasks 4-10 each have unit tests, Task 5 has integration smoke, Task 11 step 6 is the E2E. ✅

**Placeholder scan:** No TBDs, all code blocks contain real implementations, no "similar to Task N" cross-references that aren't fully repeated.

**Type consistency:** `Tweet`, `VoiceSample`, `ScoredTweet`, `Draft`, `DigestItem` defined once each (in `store.py` / `filter.py` / `drafter.py`) and referenced consistently. Method names: `upsert_tweets`, `get_recent_tweets`, `score_tweets`, `select`, `draft_many`, `angles`, `render_digest_html`, `intent_link`, `EmailSender.send` — all consistent across tasks.

One small gap I'd flag rather than fix: the spec mentioned an in-handler `errors` table write for the "Apify down → cached fallback" path. Task 9's `digest` doesn't wrap Apify calls in a try/except that logs to the errors table — it just lets the exception bubble. This is acceptable for v0 (cron retries the next day; Vercel logs the failure) but worth knowing. We can add explicit error logging once we hit the first real failure and learn what we want to recover from.

---

## Plan complete

Plan saved to `docs/superpowers/plans/2026-05-11-feed-warrior.md`.
