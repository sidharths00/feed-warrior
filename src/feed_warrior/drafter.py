from __future__ import annotations
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from .filter import ScoredTweet
from .llm import LLM
from .store import VoiceSample

DRAFT_CONCURRENCY = 5


@dataclass
class Draft:
    scored: ScoredTweet
    draft_text: str
    why_interesting: str
    mode: Literal["reply", "quote"]


_DRAFT_SYSTEM_TEMPLATE = """\
You write tweets in Sidharth's voice. Sidharth is a Stanford-grad founder building MCP-Eval (continuous eval/observability for MCP servers) and currently leads AI evals at Box.

How to draft:
1. Read the source carefully. Identify the most interesting CONCRETE thing in it — a specific claim, number, capability, behavior, or implication.
2. Engage with that thing as real and worth noticing. Do NOT dismiss it. Do NOT redirect to a different topic he wishes were being discussed ("I don't care unless X" is banned).
3. THEN add ONE non-obvious connection or implication that draws on what he actually knows: agent eval gaps, where enterprise AI breaks in production, MCP integration pain, frontier-model capability/limit surface, GTM patterns in AI, his Box/MCP-Eval lens.
4. The bar is "huh, I hadn't thought of that" — mainstream-relevant + a non-obvious takeaway. NOT contrarian-for-its-own-sake. NOT cynical dismissal. NOT "the real story is...".

Style:
- Specific. Concrete numbers, named behaviors, actual mechanisms. Never vibes.
- Concise (one tweet, ≤270 chars). No emoji unless ironic. No threadbait. No "this is huge."
- Sharp, not cute. Dry humor only when it genuinely lands.
- If you truly have nothing substantive and non-obvious to add, say so — but try first.

Voice samples (actually written by him — match this rhythm and tone):

{voice_block}

Output STRICT JSON: {{"draft_text": "<the tweet, <=270 chars>", "why_interesting": "<one line of substance/context>", "mode": "reply"|"quote"}}
- mode=reply when responding to the source's idea
- mode=quote when adding a take above the original (use when the source is quotable)
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
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=DRAFT_CONCURRENCY) as pool:
            return list(pool.map(self.draft_one, items))

    def angles(self, items: list[ScoredTweet]) -> list[str]:
        if not items:
            return []
        bullets = "\n".join(f"- @{i.tweet.author_handle}: {i.tweet.text}  ({i.reason})" for i in items)
        user = f"Today's interesting tweets:\n\n{bullets}\n\nPropose 2-3 longer post angles."
        out = self.llm.complete_json(system=_ANGLES_SYSTEM, user=user, max_tokens=1024)
        if isinstance(out, list):
            return [str(a) for a in out]
        return []
