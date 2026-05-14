from datetime import datetime, timezone
from unittest.mock import MagicMock
from feed_warrior.drafter import Drafter, Draft
from feed_warrior.filter import ScoredTweet
from feed_warrior.store import Tweet, VoiceSample


def _scored(id: str = "1", text: str = "interesting tweet") -> ScoredTweet:
    t = Tweet(id=id, author_handle="karpathy", text=text, url=f"https://x.com/karpathy/status/{id}",
              posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc), source="list")
    return ScoredTweet(tweet=t, scores={"signal": 8, "work_adjacent": 2, "discourse": 1}, reason="novel")


def test_voice_corpus_block_renders_examples():
    samples = [
        VoiceSample(id="a", text="Eval coverage is a vibe.", posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        VoiceSample(id="b", text="Most agent demos are fictional.", posted_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    block = Drafter._voice_block(samples)
    assert "Eval coverage" in block
    assert "fictional" in block


def test_draft_one_calls_llm_and_returns_draft():
    llm = MagicMock()
    llm.complete_json.return_value = {
        "draft_text": "the eval gap is real",
        "why_interesting": "shows why offline metrics mislead",
        "mode": "reply",
    }
    d = Drafter(llm=llm, voice_samples=[])
    draft = d.draft_one(_scored())
    assert draft.draft_text == "the eval gap is real"
    assert draft.mode in ("reply", "quote")


def test_draft_many_returns_one_per_input():
    llm = MagicMock()
    # draft_many calls draft_and_refine_one for each item: 1 draft call + 1 refine call.
    llm.complete_json.side_effect = lambda system, user, max_tokens=None: (
        {"draft_text": "x", "why_interesting": "y", "mode": "reply"}
        if "Source tweet" in user and "Tighten" not in user
        else {"refined": "x-refined", "changed": True, "notes": "tightened"}
    )
    d = Drafter(llm=llm, voice_samples=[])
    drafts = d.draft_many([_scored("1"), _scored("2"), _scored("3")])
    assert len(drafts) == 3
    # All drafts went through refine
    assert all(dr.draft_text == "x-refined" for dr in drafts)


def test_refine_one_keeps_substance_swaps_text():
    from feed_warrior.drafter import Draft as DraftCls
    base = DraftCls(scored=_scored(), draft_text="the real signal here is X", why_interesting="why", mode="reply")
    llm = MagicMock()
    llm.complete_json.return_value = {"refined": "X. that's the signal.", "changed": True, "notes": "cut filler opener"}
    d = Drafter(llm=llm, voice_samples=[])
    refined = d.refine_one(base)
    assert refined.draft_text == "X. that's the signal."
    assert refined.why_interesting == "why"  # unchanged
    assert refined.mode == "reply"           # unchanged
    assert refined.scored is base.scored     # unchanged


def test_refine_one_returns_original_on_llm_failure():
    from feed_warrior.drafter import Draft as DraftCls
    base = DraftCls(scored=_scored(), draft_text="original take", why_interesting="why", mode="reply")
    llm = MagicMock()
    llm.complete_json.side_effect = RuntimeError("boom")
    d = Drafter(llm=llm, voice_samples=[])
    refined = d.refine_one(base)
    assert refined.draft_text == "original take"


def test_angles_returns_list():
    llm = MagicMock()
    llm.complete_json.return_value = ["angle one", "angle two", "angle three"]
    d = Drafter(llm=llm, voice_samples=[])
    angles = d.angles([_scored("1"), _scored("2")])
    assert angles == ["angle one", "angle two", "angle three"]
