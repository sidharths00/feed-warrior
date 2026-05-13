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
