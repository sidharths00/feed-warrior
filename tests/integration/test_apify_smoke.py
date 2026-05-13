import os
from datetime import datetime, timedelta, timezone
import pytest
from feed_warrior.apify_client import ApifyClient

pytestmark = pytest.mark.skipif(not os.getenv("APIFY_TOKEN"), reason="needs APIFY_TOKEN")


def test_fetch_known_account_returns_tweets():
    client = ApifyClient(token=os.environ["APIFY_TOKEN"])
    since = datetime.now(timezone.utc) - timedelta(days=7)
    tweets = client.fetch_account_tweets(["karpathy"], since=since, max_per_handle=5)
    assert len(tweets) > 0
    t = tweets[0]
    assert t.author_handle == "karpathy"
    assert t.url.startswith("https://x.com/")
    assert t.text
