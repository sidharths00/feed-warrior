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
