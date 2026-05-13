from __future__ import annotations
from pathlib import Path
from typing import Any
from urllib.parse import quote

import resend
from jinja2 import Environment, FileSystemLoader

from .drafter import Draft

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


def intent_link(text: str) -> str:
    return f"https://twitter.com/intent/tweet?text={quote(text, safe='')}"


def render_digest_html(drafts: list[Draft], angles: list[str], date_str: str) -> str:
    tmpl = _env.get_template("digest.html.j2")
    return tmpl.render(drafts=drafts, angles=angles, date_str=date_str, intent_link=intent_link)


class EmailSender:
    def __init__(self, resend_client: Any | None = None, api_key: str | None = None,
                 recipient: str = "", from_addr: str = "Feed Warrior <feed@feedwarrior.dev>"):
        if resend_client is None:
            resend.api_key = api_key
            self._client = resend
        else:
            self._client = resend_client
        self.recipient = recipient
        self.from_addr = from_addr

    def send(self, subject: str, html: str) -> dict:
        return self._client.Emails.send({
            "from": self.from_addr,
            "to": [self.recipient],
            "subject": subject,
            "html": html,
        })
