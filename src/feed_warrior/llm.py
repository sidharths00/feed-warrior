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
