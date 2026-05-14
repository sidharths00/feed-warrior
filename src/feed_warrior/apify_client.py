from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from apify_client import ApifyClient as ApifySDK

from .store import Tweet, VoiceSample

DEFAULT_TWEET_ACTOR = "apidojo/tweet-scraper"
DEFAULT_FOLLOWS_ACTOR = "igview-owner/twitter-x-following-scraper"


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
        handle_list = list(handles)
        run_input = {
            "twitterHandles": handle_list,
            "maxItems": max_per_handle * len(handle_list) if handle_list else 100,
            "sort": "Latest",
            "tweetLanguage": "en",
            "since": since.isoformat(),
        }
        run = self._client.actor(self.actor_id_account).call(run_input=run_input)
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        return self._parse_tweets(items, source="list")

    def search_tweets(self, queries: Iterable[str], since: datetime, max_per_query: int = 20) -> list[Tweet]:
        query_list = list(queries)
        run_input = {
            "searchTerms": query_list,
            "maxItems": max_per_query * max(1, len(query_list)),
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
        run_input = {"usernames": [handle], "max_following_per_user": max_items}
        run = self._client.actor(self.actor_id_follows).call(run_input=run_input)
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        return items

    @staticmethod
    def _parse_tweets(raw: list[dict], source: Literal["list", "search"]) -> list[Tweet]:
        out: list[Tweet] = []
        for it in raw:
            tid = str(it.get("id") or it.get("tweetId") or "")
            author_obj = it.get("author") or {}
            author = author_obj.get("userName") or it.get("authorHandle") or ""
            text = it.get("text") or it.get("fullText") or ""
            url = it.get("url") or (f"https://x.com/{author}/status/{tid}" if author and tid else "")
            posted = _parse_dt(it.get("createdAt"))
            if not (tid and author and text and url and posted):
                continue
            view_count = it.get("viewCount")
            like_count = it.get("likeCount")
            author_followers = author_obj.get("followers") or author_obj.get("followers_count")
            out.append(Tweet(
                id=tid, author_handle=author, text=text, url=url, posted_at=posted, source=source,
                view_count=int(view_count) if view_count is not None else None,
                like_count=int(like_count) if like_count is not None else None,
                author_followers=int(author_followers) if author_followers is not None else None,
            ))
        return out


def _parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    s = str(s)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        # Twitter API format e.g. "Tue May 12 18:31:09 +0000 2026"
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None
