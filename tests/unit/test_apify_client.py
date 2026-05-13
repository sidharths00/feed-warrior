from datetime import datetime, timezone
from unittest.mock import MagicMock
from feed_warrior.apify_client import ApifyClient
from feed_warrior.store import Tweet


def test_parse_tweets_from_actor_output():
    raw = [
        {
            "id": "111",
            "author": {"userName": "karpathy"},
            "text": "hello",
            "url": "https://x.com/karpathy/status/111",
            "createdAt": "2026-05-11T10:00:00.000Z",
        },
        {
            "id": "222",
            "author": {"userName": "swyx"},
            "text": "world",
            "url": "https://x.com/swyx/status/222",
            "createdAt": "2026-05-11T11:00:00.000Z",
        },
    ]
    out = ApifyClient._parse_tweets(raw, source="list")
    assert len(out) == 2
    assert out[0].id == "111"
    assert out[0].author_handle == "karpathy"
    assert out[0].posted_at == datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    assert out[0].source == "list"


def test_parse_tweets_handles_twitter_date_format():
    """Apify's apidojo/tweet-scraper returns Twitter-format dates, not ISO8601."""
    raw = [{
        "id": "111",
        "author": {"userName": "karpathy"},
        "text": "hello",
        "url": "https://x.com/karpathy/status/111",
        "createdAt": "Tue May 12 18:31:09 +0000 2026",
    }]
    out = ApifyClient._parse_tweets(raw, source="list")
    assert len(out) == 1
    assert out[0].posted_at == datetime(2026, 5, 12, 18, 31, 9, tzinfo=timezone.utc)


def test_fetch_account_tweets_calls_actor_with_handles():
    apify = MagicMock()
    actor = MagicMock()
    apify.actor.return_value = actor
    actor.call.return_value = {"defaultDatasetId": "ds-1"}
    dataset = MagicMock()
    apify.dataset.return_value = dataset
    dataset.iterate_items.return_value = iter([])
    client = ApifyClient(client=apify, actor_id_account="apidojo/tweet-scraper")
    client.fetch_account_tweets(["karpathy", "swyx"], since=datetime(2026, 5, 10, tzinfo=timezone.utc))
    apify.actor.assert_called_with("apidojo/tweet-scraper")
    args, kwargs = actor.call.call_args
    payload = kwargs.get("run_input") or args[0]
    assert "karpathy" in str(payload)
    assert "swyx" in str(payload)
