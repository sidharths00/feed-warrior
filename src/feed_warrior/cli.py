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
    # check=check_connection pings each connection before handing it out, so
    # connections that Neon idle-killed during a long Apify scrape get rebuilt.
    return ConnectionPool(
        cfg.database_url,
        min_size=1,
        max_size=4,
        open=True,
        check=ConnectionPool.check_connection,
    )


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
            {"handle": f.get("screen_name") or f.get("userName") or "",
             "name": f.get("name", ""),
             "bio": (f.get("description") or "")[:200],
             "followers": f.get("followers_count") or f.get("followersCount") or 0}
            for f in batch if (f.get("screen_name") or f.get("userName"))
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


MAX_ACCOUNTS = 50
MAX_PER_HANDLE = 5
MAX_CANDIDATES = 100
MIN_AUTHOR_FOLLOWERS = int(os.getenv("MIN_AUTHOR_FOLLOWERS", "2000"))
MIN_VIEW_COUNT = int(os.getenv("MIN_VIEW_COUNT", "1000"))


def _passes_quality(t) -> bool:
    """Drop noise: tweet must come from a non-trivial account OR have real reach."""
    followers = t.author_followers or 0
    views = t.view_count or 0
    return followers >= MIN_AUTHOR_FOLLOWERS or views >= MIN_VIEW_COUNT


def _with_store(cfg: Config, fn):
    """Run fn(store) with a fresh, short-lived pool. Avoids stale-connection issues."""
    pool = _pool(cfg)
    try:
        return fn(Store(pool))
    finally:
        pool.close()


@main.command("digest")
@click.option("--dry-run", is_flag=True, help="Render but do not send; writes out/preview.html")
def digest(dry_run: bool):
    """Run the daily pipeline."""
    cfg = Config.from_env()
    apify = ApifyClient(token=cfg.apify_token)
    llm = LLM(api_key=cfg.anthropic_api_key)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Phase 1: read accounts + voice corpus
    accounts, voice = _with_store(cfg, lambda s: (s.get_active_accounts()[:MAX_ACCOUNTS], s.get_voice_samples(limit=200)))
    click.echo(f"fetching from {len(accounts)} accounts + {len(cfg.keywords)} keywords since {since.isoformat()}")

    # Phase 2: Apify scrape (long-running, no DB held open)
    new_tweets: list = []
    if accounts:
        new_tweets += apify.fetch_account_tweets(accounts, since=since, max_per_handle=MAX_PER_HANDLE)
    if cfg.keywords:
        new_tweets += apify.search_tweets(cfg.keywords, since=since)
    click.echo(f"apify returned {len(new_tweets)} tweets")

    # Phase 3: persist + read candidates, then quality-gate (fresh pool)
    raw_candidates = _with_store(cfg, lambda s: (s.upsert_tweets(new_tweets), s.get_recent_tweets(since=since))[1])
    candidates = [t for t in raw_candidates if _passes_quality(t)][:MAX_CANDIDATES]
    click.echo(f"scoring {len(candidates)}/{len(raw_candidates)} candidates "
               f"(quality gate: ≥{MIN_AUTHOR_FOLLOWERS} followers OR ≥{MIN_VIEW_COUNT} views; cap {MAX_CANDIDATES})")

    # Phase 4: score + select + draft (no DB)
    filt = Filter(llm=llm)
    scored = filt.score_tweets(candidates)
    chosen = filt.select(scored, weights=cfg.bucket_weights, total=cfg.daily_slots)
    click.echo(f"selected {len(chosen)}")

    drafter = Drafter(llm=llm, voice_samples=voice)
    drafts = drafter.draft_many(chosen)
    angles = drafter.angles(chosen)
    click.echo(f"drafted {len(drafts)}; {len(angles)} angles")

    # Phase 5: render
    date_str = datetime.now(timezone.utc).date().isoformat()
    html = render_digest_html(drafts=drafts, angles=angles, date_str=date_str)

    if dry_run:
        out_path = Path("out/preview.html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        click.echo(f"dry run: wrote {out_path}")
        return

    # Phase 6: send + record (fresh pool)
    sender = EmailSender(api_key=cfg.resend_api_key, recipient=cfg.recipient_email,
                         from_addr=os.getenv("FROM_ADDR", "Feed Warrior <onboarding@resend.dev>"))
    sender.send(subject=f"Feed Warrior — {date_str} ({len(drafts)} drafts)", html=html)
    from .store import DigestItem

    def _record(s: Store):
        digest_id = s.create_digest(status="sent")
        s.add_digest_items([
            DigestItem(digest_id=digest_id, tweet_id=d.scored.tweet.id, draft_text=d.draft_text,
                       why_interesting=d.why_interesting, scores=d.scored.scores)
            for d in drafts
        ])
        return digest_id
    digest_id = _with_store(cfg, _record)
    click.echo(f"sent digest {digest_id}")


if __name__ == "__main__":
    main()
