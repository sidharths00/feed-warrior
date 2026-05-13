import json
import pytest
from unittest.mock import MagicMock, patch
from anthropic import APIConnectionError, AuthenticationError
from feed_warrior.llm import LLM, MAX_RETRIES


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _retriable_error():
    return APIConnectionError(request=MagicMock())


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


def test_llm_complete_json_extracts_from_prose():
    client = MagicMock()
    client.messages.create.return_value = _mock_response('Sure, here you go:\n{"a": 1}\nLet me know!')
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_json(system="s", user="u") == {"a": 1}


@patch("feed_warrior.llm.time.sleep", lambda *a, **k: None)
def test_llm_retries_on_retriable_failure():
    client = MagicMock()
    client.messages.create.side_effect = [
        _retriable_error(),
        _retriable_error(),
        _mock_response("ok"),
    ]
    llm = LLM(client=client, model="claude-sonnet-4-6")
    assert llm.complete_text(system="s", user="u") == "ok"
    assert client.messages.create.call_count == 3


@patch("feed_warrior.llm.time.sleep", lambda *a, **k: None)
def test_llm_raises_after_max_retries():
    client = MagicMock()
    client.messages.create.side_effect = _retriable_error()
    llm = LLM(client=client, model="claude-sonnet-4-6")
    with pytest.raises(RuntimeError, match="failed after 3"):
        llm.complete_text(system="s", user="u")
    assert client.messages.create.call_count == MAX_RETRIES


def test_llm_does_not_retry_non_retriable_errors():
    client = MagicMock()
    client.messages.create.side_effect = AuthenticationError(
        message="bad key", response=MagicMock(), body=None
    )
    llm = LLM(client=client, model="claude-sonnet-4-6")
    with pytest.raises(AuthenticationError):
        llm.complete_text(system="s", user="u")
    assert client.messages.create.call_count == 1
