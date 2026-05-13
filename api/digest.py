"""Vercel Function entry. Triggered by Vercel Cron daily at 14:00 UTC.

Auth: requires `Authorization: Bearer <CRON_SECRET>` header (Vercel Cron sets this automatically when you set CRON_SECRET env var).
"""
from __future__ import annotations
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

# Ensure src is importable on Vercel
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feed_warrior.cli import main as cli_main  # noqa: E402
from click.testing import CliRunner  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        return self._run()

    def do_GET(self):
        return self._run()

    def _run(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")
        if not secret or auth != f"Bearer {secret}":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        try:
            runner = CliRunner()
            result = runner.invoke(cli_main, ["digest"], catch_exceptions=False)
            body = {"exit_code": result.exit_code, "output": result.output}
            self.send_response(200 if result.exit_code == 0 else 500)
        except Exception as e:
            body = {"error": str(e), "trace": traceback.format_exc()}
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
