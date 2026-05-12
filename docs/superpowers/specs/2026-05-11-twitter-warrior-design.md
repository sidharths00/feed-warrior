# Twitter Warrior — Design Spec

**Date:** 2026-05-11
**Owner:** Sidharth Srinivasan (`@sidharths00`)
**Status:** Approved for implementation

---

## Purpose

A daily content engine that surfaces interesting AI tweets from the accounts and topics Sidharth cares about, drafts replies / quote-tweets / longer post angles in his voice, and emails them to him in a format that lets him post from his phone with one tap.

Goal: lower the activation energy of putting out substantive AI content. Not parroting — adding a take. Funny is fine.

## Non-goals

- A dashboard or admin UI in v0 (config lives in files).
- Auto-posting to X (drafts only; user posts manually via tweet-intent links).
- A "did you actually post it" feedback loop in v0 (schema supports it; not wired).
- Auto-refreshing the voice corpus (manual `bootstrap-corpus` re-run).
- Multi-user / multi-tenant (single user: Sidharth).

## Inputs

- **Curated account list** — built from Sidharth's X follows, LLM-classified for AI relevance, manually pruned. Stored in `accounts` table.
- **Topic search keywords** — defaults: `MCP`, `agent evals`, `Claude`, `Anthropic`, `OpenAI`, `Cursor`, `frontier model`, lab names. Stored in config.
- **Voice corpus** — ~500 of Sidharth's own past tweets, scraped once via Apify, used as system-prompt context for drafting.
- **Filter weights** — 50% signal-rich AI takes / 30% work-adjacent (MCP, evals, enterprise AI) / 20% discourse & drama. Tunable in config.

## Output

A daily email (~7am PT) containing:

- 5-8 **draft items**, each with:
  - Source tweet (author + text + link to original on X)
  - Drafted reply or quote-tweet text in Sidharth's voice
  - "Post this draft" link — `https://twitter.com/intent/tweet?text=<urlencoded>` — opens X compose on phone with the draft pre-filled
  - One-line "why this is interesting" rationale
- 2-3 **longer post angles** at the bottom — themes pulled from the day's tweets that could become threads or longer posts (not pre-drafted in full, just the angle).

Plus an on-demand CLI (`twitter-warrior digest`) that runs the same pipeline at any time.

## Stack

- **Language:** Python 3.13 (matches mcp-eval)
- **Compute:** Vercel Functions (Fluid Compute, Python runtime)
- **Scheduling:** Vercel Cron — `0 14 * * *` UTC (7am PT)
- **Database:** Neon Postgres (Vercel Marketplace, free tier)
- **Email:** Resend (Vercel Marketplace, free tier)
- **Scraping:** Apify (existing $29/mo subscription — Twitter scraper actors)
- **LLM:** Claude Sonnet 4.6 via Vercel AI Gateway (`anthropic/claude-sonnet-4-6`)

## Architecture

### Components (each has one responsibility)

| File | Job |
|---|---|
| `apify_client.py` | Wrapper for Apify actor calls: `fetch_account_tweets(handles, since)`, `search_tweets(queries, since)`, `fetch_user_tweets(handle, n)`, `fetch_follows(handle)` |
| `store.py` | Postgres I/O for `tweets`, `voice_samples`, `accounts`, `digests`, `digest_items`, `errors` |
| `filter.py` | Batched LLM scoring + bucket selection. Input: candidate tweets. Output: top-N per bucket per the 50/30/20 weights. |
| `drafter.py` | LLM drafting in Sidharth's voice. Two prompts: (1) per-tweet draft + rationale, (2) end-of-day longer post angles. |
| `email.py` | Markdown→HTML rendering, intent-link encoding, Resend send |
| `cli.py` | Local commands: `bootstrap-corpus`, `bootstrap-accounts`, `digest --dry-run`, `digest` |
| `api/digest.py` | Vercel function entrypoint: orchestrates the pipeline |
| `config.py` | Env loading + config file parsing (keywords, weights) |

### Data flow (daily run)

```
Vercel Cron (14:00 UTC daily)
  └─→ POST /api/digest
        ├─→ apify_client.fetch_account_tweets(curated, since=24h)
        ├─→ apify_client.search_tweets(keywords, since=24h)
        ├─→ store.upsert_tweets(...)              # dedup by tweet ID
        ├─→ filter.score_and_bucket(new tweets)   # batched LLM, 50/30/20
        ├─→ drafter.draft(top items, voice corpus) # parallel LLM calls
        ├─→ drafter.angles(themes)                # 2-3 longer takes
        ├─→ email.render(drafts, angles)
        ├─→ resend.send(to=sidharths00@gmail.com)
        └─→ store.record_digest(...)
```

### Schema

```sql
CREATE TABLE tweets (
  id            TEXT PRIMARY KEY,           -- X tweet ID
  author_handle TEXT NOT NULL,
  text          TEXT NOT NULL,
  url           TEXT NOT NULL,
  posted_at     TIMESTAMPTZ NOT NULL,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source        TEXT NOT NULL               -- 'list' | 'search'
);
CREATE INDEX tweets_posted_at_idx ON tweets (posted_at DESC);

CREATE TABLE voice_samples (
  id        TEXT PRIMARY KEY,
  text      TEXT NOT NULL,
  posted_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE accounts (
  handle    TEXT PRIMARY KEY,
  added_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE digests (
  id      SERIAL PRIMARY KEY,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status  TEXT NOT NULL                     -- 'sent' | 'failed' | 'partial'
);

CREATE TABLE digest_items (
  id              SERIAL PRIMARY KEY,
  digest_id       INTEGER NOT NULL REFERENCES digests(id),
  tweet_id        TEXT NOT NULL REFERENCES tweets(id),
  draft_text      TEXT NOT NULL,
  why_interesting TEXT NOT NULL,
  scores          JSONB NOT NULL            -- {signal, work_adjacent, discourse}
);

CREATE TABLE errors (
  id         SERIAL PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  component  TEXT NOT NULL,
  message    TEXT NOT NULL,
  context    JSONB
);
```

### Filter logic

- Score every new tweet from the last 24h with one batched LLM call per ~20 tweets.
- For each tweet, return scores 0-10 for `signal`, `work_adjacent`, `discourse`, plus a one-line reason.
- Allocate ~50% / 30% / 20% of the daily slot count (default 7) to the three buckets, sorted by score within each bucket. Round so the total is 7.
- A tweet may belong to multiple buckets; assign it to its highest-scoring bucket to avoid duplicate selection.

### Drafting

- **Per-tweet draft:** one LLM call per chosen tweet. System prompt = voice corpus + style guidance. User prompt = source tweet + "draft a reply or quote-tweet that adds substance, optionally funny, in this voice." Output: JSON `{draft_text, why_interesting, mode: 'reply' | 'quote'}`.
- **Longer post angles:** one LLM call after drafts are done. Input: chosen tweets + their reasons. Output: 2-3 angle paragraphs ("if you wanted to write a thread, here's the take").
- Per-tweet drafts run in parallel (`asyncio.gather`) — bounded by a semaphore of 5 to stay polite to the API.

### Email format

Markdown → HTML, mobile-friendly. Each draft item is a card:

```
─────────────────────────────────
🔥 Source (@karpathy):
"<original tweet text>"
→ View on X

✍️ Draft:
"<draft in your voice>"
→ Post this draft  ← tweet-intent link

💭 Why interesting:
<one-line rationale>
─────────────────────────────────
```

Footer: 2-3 longer-post angles, plain text.

## Error handling

| Failure | Behavior |
|---|---|
| Apify API down | Fall back to cached tweets from last 24h; banner in email "Apify unavailable, partial digest" |
| LLM call fails | Retry 3x with exponential backoff; if still failing, skip that draft and proceed |
| Resend API down | Persist digest to Postgres; next cron retries the send |
| Postgres down | Log to Vercel logs; cron exits non-zero (Vercel will surface alert) |
| All errors | Logged to Vercel logs and `errors` table |

## Testing

- **Unit:** pure-function tests for filter bucket math, intent-link URL encoding, email-template rendering. No network.
- **Integration:** real Apify call to a known stable account (e.g., `@karpathy`), assert parse shape. Real Postgres roundtrip for store layer (skipped without `DATABASE_URL`).
- **E2E:** `digest --dry-run` runs the full pipeline against a fixture set of tweets, writes the rendered email to `out/preview.html`, no send. Used for visual review.

## Bootstrap (one-time setup)

1. **Voice corpus:** `twitter-warrior bootstrap-corpus` → Apify scrapes last ~500 tweets from `@sidharths00`, populates `voice_samples`.
2. **Curated accounts:**
   - `twitter-warrior bootstrap-accounts` → Apify scrapes who `@sidharths00` follows.
   - For each followed account, Apify also pulls bio + last 5 tweets.
   - LLM classifies each as `ai_relevant: yes/no/maybe` with a one-line reason. Cost: ~$1-3.
   - Output written to `accounts_seed.md` for manual pruning.
   - `twitter-warrior load-accounts <file>` ingests the approved list into `accounts`.

## Repo layout

```
twitter-warrior/
├── api/
│   └── digest.py                    # Vercel function entry
├── src/twitter_warrior/
│   ├── __init__.py
│   ├── apify_client.py
│   ├── store.py
│   ├── filter.py
│   ├── drafter.py
│   ├── email.py
│   ├── cli.py
│   └── config.py
├── migrations/
│   └── 001_init.sql
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/superpowers/specs/
│   └── 2026-05-11-twitter-warrior-design.md
├── pyproject.toml
├── vercel.ts
├── .env.example
├── .gitignore
└── README.md
```

## Configuration

- `KEYWORDS` (env var, comma-separated): topic search terms
- `BUCKET_WEIGHTS` (env var, JSON): `{"signal": 0.5, "work_adjacent": 0.3, "discourse": 0.2}`
- `DAILY_SLOTS` (env var, int, default 7): number of draft items per email
- `RECIPIENT_EMAIL` (env var): where the digest goes
- `APIFY_TOKEN`, `RESEND_API_KEY`, `DATABASE_URL`, `AI_GATEWAY_API_KEY`: secrets
- `CRON_SECRET`: shared secret to authorize `/api/digest` calls (so Cron + CLI can hit it but randos can't)

## Calibration loop (manual, post-v0)

After receiving N digests, Sidharth tells the assistant "less of X, more of Y." We adjust:
- Bucket weights (`BUCKET_WEIGHTS`)
- Filter prompt (what counts as "signal-rich")
- Drafter prompt (voice nudges)
- Curated list (add/remove handles)

Schema supports a future tightening loop: log which drafts get posted (could be inferred by polling Sidharth's posted tweets and matching against drafts) → train a preference model. Out of scope for v0.

## Open follow-ups (post-v0, not blockers)

- Next.js admin dashboard for tuning weights, managing curated list, viewing past digests
- Auto-update voice corpus weekly
- Inferred "did you post it" loop using Apify scrape of Sidharth's own tweets
- Multi-recipient (e.g., team digest)
- Slack delivery option
