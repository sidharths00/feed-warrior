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
            max_tokens = max(2048, len(batch) * 120)
            scores = self.llm.complete_json(system=SCORING_SYSTEM, user=user, max_tokens=max_tokens)
            if not isinstance(scores, list):
                continue
            by_id = {s["id"]: s for s in scores if isinstance(s, dict) and "id" in s}
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
        # Precondition: weights sum to ~1. Config validates this; we re-check defensively.
        if not 0.99 < sum(weights[k] for k in BUCKETS) < 1.01:
            raise ValueError(f"weights must sum to 1, got {sum(weights[k] for k in BUCKETS)}")
        raw = {k: weights[k] * total for k in BUCKETS}
        floors = {k: int(math.floor(v)) for k, v in raw.items()}
        remaining = max(0, total - sum(floors.values()))
        fracs = sorted(((raw[k] - floors[k], k) for k in BUCKETS), reverse=True)
        for _, k in fracs[:remaining]:
            floors[k] += 1
        return floors

    @staticmethod
    def _pick_top_per_bucket(scored: list[ScoredTweet], counts: dict[str, int]) -> list[ScoredTweet]:
        by_bucket: dict[str, list[ScoredTweet]] = {b: [] for b in BUCKETS}
        for s in scored:
            top_bucket = max(BUCKETS, key=lambda b: s.scores.get(b, 0))
            by_bucket[top_bucket].append(s)
        for b in BUCKETS:
            by_bucket[b].sort(key=lambda s: s.scores.get(b, 0), reverse=True)

        picked: list[ScoredTweet] = []
        used: set[str] = set()
        for b in BUCKETS:
            for s in by_bucket[b][: counts[b]]:
                picked.append(s)
                used.add(s.tweet.id)
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
