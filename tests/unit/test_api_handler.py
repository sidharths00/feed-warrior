import os
import sys
import io
from unittest.mock import patch, MagicMock
from http.server import BaseHTTPRequestHandler

# Ensure repo root is on sys.path so `api` is importable as a top-level package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _invoke_handler(method: str, headers: dict):
    from api import digest as digest_module
    h = digest_module.handler.__new__(digest_module.handler)
    h.headers = headers
    h.send_response = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()
    h.wfile = io.BytesIO()
    if method == "GET":
        h.do_GET()
    else:
        h.do_POST()
    return h


def test_handler_rejects_missing_auth(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    h = _invoke_handler("POST", {"Authorization": ""})
    h.send_response.assert_called_with(401)


def test_handler_rejects_bad_auth(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    h = _invoke_handler("POST", {"Authorization": "Bearer wrong"})
    h.send_response.assert_called_with(401)
