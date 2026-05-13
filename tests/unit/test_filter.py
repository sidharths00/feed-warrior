from datetime import datetime, timezone
from unittest.mock import MagicMock
from feed_warrior.filter import Filter, ScoredTweet
from feed_warrior.store import Tweet


def _t(id: str, text: str = "x") -> Tweet:
    return Tweet(id=id, author_handle="a", text=text, url="u", posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc), source="list")


def test_bucket_allocation_50_30_20_seven_slots():
    weights = {"signal": 0.5, "work_adjacent": 0.3, "discourse": 0.2}
    counts = Filter._allocate_slots(weights, total=7)
    assert counts == {"signal": 4, "work_adjacent": 2, "discourse": 1}
    assert sum(counts.values()) == 7


def test_bucket_allocation_5_slots():
    weights = {"signal": 0.5, "work_adjacent": 0.3, "discourse": 0.2}
    counts = Filter._allocate_slots(weights, total=5)
    assert sum(counts.values()) == 5


def test_pick_top_per_bucket_assigns_to_highest_scoring_bucket():
    scored = [
        ScoredTweet(tweet=_t("1"), scores={"signal": 9, "work_adjacent": 2, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("2"), scores={"signal": 1, "work_adjacent": 8, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("3"), scores={"signal": 1, "work_adjacent": 1, "discourse": 9}, reason=""),
        ScoredTweet(tweet=_t("4"), scores={"signal": 7, "work_adjacent": 3, "discourse": 1}, reason=""),
    ]
    counts = {"signal": 2, "work_adjacent": 1, "discourse": 1}
    picked = Filter._pick_top_per_bucket(scored, counts)
    ids = [p.tweet.id for p in picked]
    assert "1" in ids and "4" in ids and "2" in ids and "3" in ids
    assert len(picked) == 4


def test_pick_top_falls_back_when_bucket_short():
    scored = [
        ScoredTweet(tweet=_t("1"), scores={"signal": 9, "work_adjacent": 1, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("2"), scores={"signal": 8, "work_adjacent": 1, "discourse": 1}, reason=""),
        ScoredTweet(tweet=_t("3"), scores={"signal": 1, "work_adjacent": 1, "discourse": 9}, reason=""),
    ]
    counts = {"signal": 1, "work_adjacent": 0, "discourse": 2}
    picked = Filter._pick_top_per_bucket(scored, counts)
    ids = sorted([p.tweet.id for p in picked])
    assert ids == ["1", "2", "3"]


def test_score_tweets_uses_llm():
    llm = MagicMock()
    llm.complete_json.return_value = [
        {"id": "1", "signal": 8, "work_adjacent": 3, "discourse": 1, "reason": "novel insight"},
        {"id": "2", "signal": 2, "work_adjacent": 1, "discourse": 9, "reason": "drama"},
    ]
    filt = Filter(llm=llm)
    scored = filt.score_tweets([_t("1", "tweet one"), _t("2", "tweet two")])
    assert len(scored) == 2
    assert scored[0].scores["signal"] == 8
    assert scored[1].reason == "drama"
