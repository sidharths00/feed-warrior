from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import urllib.parse
from feed_warrior.email import EmailSender, render_digest_html, intent_link
from feed_warrior.drafter import Draft
from feed_warrior.filter import ScoredTweet
from feed_warrior.store import Tweet


def _draft(text: str = "my take") -> Draft:
    t = Tweet(id="1", author_handle="karpathy", text="original", url="https://x.com/karpathy/status/1",
              posted_at=datetime(2026, 5, 11, tzinfo=timezone.utc), source="list")
    s = ScoredTweet(tweet=t, scores={"signal": 8, "work_adjacent": 2, "discourse": 1}, reason="novel")
    return Draft(scored=s, draft_text=text, why_interesting="why", mode="reply")


def test_intent_link_url_encodes():
    link = intent_link("hello world & friends")
    assert link.startswith("https://twitter.com/intent/tweet?text=")
    assert urllib.parse.unquote(link.split("text=", 1)[1]) == "hello world & friends"


def test_render_digest_html_includes_drafts_and_links():
    html = render_digest_html(drafts=[_draft("draft text")], angles=["angle 1"], date_str="2026-05-11")
    assert "draft text" in html
    assert "@karpathy" in html
    assert "twitter.com/intent/tweet?text=" in html
    assert "angle 1" in html
    assert "2026-05-11" in html


def test_render_handles_empty_drafts_gracefully():
    html = render_digest_html(drafts=[], angles=[], date_str="2026-05-11")
    assert "no drafts" in html.lower() or "0 drafts" in html.lower()


def test_email_sender_calls_resend():
    resend = MagicMock()
    sender = EmailSender(resend_client=resend, recipient="me@example.com", from_addr="feed@feedwarrior.dev")
    sender.send(subject="Feed Warrior — 2026-05-11", html="<p>hi</p>")
    resend.Emails.send.assert_called_once()
    payload = resend.Emails.send.call_args[0][0]
    assert payload["to"] == ["me@example.com"]
    assert payload["subject"] == "Feed Warrior — 2026-05-11"
