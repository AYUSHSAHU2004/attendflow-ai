#!/usr/bin/env python3
"""Check a private AttendFlow URL without asking the LLM. Uses only the standard library."""

import argparse
import getpass
import json
import os
import re
import sys
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    # Keep credential and session requests on the operator-provided origin.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SmokeFailure(Exception):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="The HTTPS origin of the private demo")
    parser.add_argument(
        "--initialize",
        choices=("seed", "reset"),
        help="Provision demo accounts or reset the synthetic database",
    )
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
    cookies = CookieJar()
    opener = build_opener(NoRedirect, HTTPCookieProcessor(cookies))
    anonymous = build_opener(NoRedirect)

    def call(path, *, method="GET", authorized=True, expected=200, data=None, headers=None):
        request_headers = {"Origin": base, **(headers or {})}
        body = None
        if data is not None:
            request_headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        client = opener if authorized else anonymous
        try:
            request = Request(base + path, headers=request_headers, method=method, data=body)
            with client.open(request, timeout=12) as r:
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

    def login(name, role):
        cookies.clear()
        result = json.loads(
            call(
                "/api/auth/login",
                method="POST",
                data={"email": f"{name}@demo.attendflow.test", "password": password},
            )
        )
        check(result.get("employee", {}).get("role") == role, "Wrong signed-in role")

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
        call("/login", authorized=False)
        call("/api/dashboard", authorized=False, expected=401)
        for path in ("/docs", "/redoc", "/openapi.json"):
            call(path, authorized=False, expected=404)
        print("PASS  public login and health, protected API, disabled API docs")

        login("priya", "payroll_admin")
        if args.initialize:
            path = "/api/seed" if args.initialize == "seed" else "/api/admin/demo/reset"
            call(path, method="POST")
            if args.initialize == "reset":
                login("priya", "payroll_admin")
            print(f"PASS  explicit demo {args.initialize} and valid employee session")

        for path in ("/dashboard", "/"):
            page = call(path)
            script = re.search(rb'<script\b[^>]*\bsrc="(/assets/[^"]+\.js)"', page)
            check(b'id="root"' in page and script is not None, f"{path}: built frontend missing")
            if path == "/dashboard":
                check(call(script[1].decode()), "Built JavaScript asset is empty")

        dashboard = json.loads(call("/api/dashboard", headers={"X-Actor-Id": "E001"}))
        check(dashboard.get("scope") == "all", "Priya dashboard did not return all teams")
        call("/api/worker/messages", expected=403)
        cycle = json.loads(call("/api/admin/scheduler/run-now?model_free=true", method="POST"))
        check(
            cycle.get("status") == "completed"
            and cycle.get("detection") == "ok"
            and cycle.get("errors") == []
            and cycle.get("investigated") == []
            and cycle.get("messages_sent") == [],
            "Scheduler cycle failed or did model work",
        )
        print("PASS  admin dashboard, header ignored, and model-free scheduler cycle")
        call("/api/auth/logout", method="POST")
        call("/api/auth/me", expected=401)
        login("amit", "worker")
        inbox = json.loads(call("/api/worker/messages"))
        check(isinstance(inbox.get("items"), list), "Amit inbox did not return messages")
        call("/api/dashboard", headers={"X-Actor-Id": "E201"}, expected=403)
        print("PASS  logout, Amit inbox, and worker role restriction")
    except (SmokeFailure, ValueError) as error:
        message = str(error) if isinstance(error, SmokeFailure) else "Invalid response format"
        print(f"FAIL  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
