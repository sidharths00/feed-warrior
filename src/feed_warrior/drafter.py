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
