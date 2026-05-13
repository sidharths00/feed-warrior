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
