#!/usr/bin/env python3
"""Check a private AttendFlow URL without asking the LLM. Uses only the standard library."""

import argparse
import base64
import getpass
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    # A redirect must never forward the shared Authorization header.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SmokeFailure(Exception):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="The HTTPS origin of the private demo")
    parser.add_argument("--initialize", choices=("seed", "reset"), help="Wipes the demo DB")
    args = parser.parse_args()
    try:
        url = urlsplit(args.url.strip())
        allowed = url.scheme == "https" or (
            url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if (
            not allowed
            or not url.hostname
            or url.username is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError
    except ValueError:
        parser.error("Give a bare HTTPS origin, or a local HTTP origin")
    base = f"{url.scheme}://{url.netloc}"
    password = os.environ.get("ATTENDFLOW_DEMO_PASSWORD") or getpass.getpass("Demo password: ")
    auth = "Basic " + base64.b64encode(f"demo:{password}".encode()).decode("ascii")
    opener = build_opener(NoRedirect)

    def call(path, *, actor=None, method="GET", authorized=True, expected=200):
        headers = {"Authorization": auth} if authorized else {}
        if actor:
            headers["X-Actor-Id"] = actor
        try:
            with opener.open(Request(base + path, headers=headers, method=method), timeout=12) as r:
                status, body = r.status, r.read()
        except HTTPError as error:
            status, body = error.code, b""
            error.close()
        except (TimeoutError, URLError, OSError):
            raise SmokeFailure(f"{method} {path}: connection failed") from None
        if status != expected:
            raise SmokeFailure(f"{method} {path}: HTTP {status}, expected {expected}")
        return body

    def check(condition, message):
        if not condition:
            raise SmokeFailure(message)

    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                health = call("/healthz", authorized=False)
                if json.loads(health) == {"status": "ok"}:
                    break
            except (SmokeFailure, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise SmokeFailure("/healthz did not become ready after about two minutes")
            time.sleep(3)
        print("PASS  public health probe")
        call("/", authorized=False, expected=401)
        call("/api/dashboard", actor="E201", authorized=False, expected=401)
        print("PASS  pages and API require demo credentials")

        if args.initialize:
            path = "/api/seed" if args.initialize == "seed" else "/api/admin/demo/reset"
            call(path, actor="E201", method="POST")
            print(f"PASS  explicit demo {args.initialize}")

        for path in ("/dashboard", "/"):
            page = call(path)
            script = re.search(rb'<script\b[^>]*\bsrc="(/assets/[^"]+\.js)"', page)
            check(b'id="root"' in page and script is not None, f"{path}: built frontend missing")
            if path == "/dashboard":
                check(call(script[1].decode()), "Built JavaScript asset is empty")
        dashboard = json.loads(call("/api/dashboard", actor="E201"))
        inbox = json.loads(call("/api/worker/messages", actor="E001"))
        check(dashboard.get("scope") == "all", "Priya dashboard did not return all teams")
        check(isinstance(inbox.get("items"), list), "Amit inbox did not return messages")
        print("PASS  frontend, Priya dashboard, and Amit inbox")

        schema = json.loads(call("/openapi.json"))
        run_now = schema.get("paths", {}).get("/api/admin/scheduler/run-now", {})
        check(
            any(
                param.get("name") == "model_free" and param.get("in") == "query"
                for param in run_now.get("post", {}).get("parameters", [])
            ),
            "The server does not advertise a model-free scheduler cycle",
        )
        cycle = json.loads(
            call("/api/admin/scheduler/run-now?model_free=true", actor="E201", method="POST")
        )
        check(
            cycle.get("status") == "completed"
            and cycle.get("detection") == "ok"
            and cycle.get("errors") == []
            and cycle.get("investigated") == []
            and cycle.get("messages_sent") == [],
            "Scheduler cycle failed or did model work",
        )
        print("PASS  model-free scheduler cycle")
    except (SmokeFailure, ValueError) as error:
        message = str(error) if isinstance(error, SmokeFailure) else "Invalid response format"
        print(f"FAIL  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
