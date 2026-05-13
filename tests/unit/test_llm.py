import json
import pytest
from unittest.mock import MagicMock, patch
from feed_warrior.llm import LLM, MAX_RETRIES


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_llm_complete_text_returns_text():
    client = MagicMock()
    client.messages.create.return_value = _mock_response("hello")
    llm = LLM(client=client, model="claude-sonnet-4-6")
    out = llm.complete_text(system="s", user="u")
    assert out == "hello"


def test_llm_complete_json_parses():
    client = MagicMock()
    client.messages.create.return_value = _mock_response('{"score": 7}')
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_json(system="s", user="u") == {"score": 7}


def test_llm_complete_json_strips_codefences():
    client = MagicMock()
    client.messages.create.return_value = _mock_response("```json\n{\"a\":1}\n```")
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_json(system="s", user="u") == {"a": 1}


@patch("feed_warrior.llm.time.sleep", lambda *a, **k: None)
def test_llm_retries_on_failure():
    from anthropic import APIError
    client = MagicMock()
    client.messages.create.side_effect = [
        Exception("transient"),
        Exception("transient"),
        _mock_response("ok"),
    ]
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_text(system="s", user="u") == "ok"
    assert client.messages.create.call_count == 3
