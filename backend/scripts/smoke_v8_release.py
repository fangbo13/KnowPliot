"""Lightweight V8 release smoke checks.

This script is intentionally dependency-light so it can run on a freshly built
release host. It can either validate frontend build artifacts only, or perform
authenticated API smoke checks against a running backend.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINTS = [
    ("health", "GET", "/admin/health/"),
    ("quality_report", "GET", "/admin/reports/knowledge-quality/"),
    ("feedback_export", "GET", "/admin/reports/export/?dataset=feedback&format=csv"),
    ("review_queue", "GET", "/admin/quality/feedback/"),
]


def _json_request(url: str, method: str = "GET", token: str | None = None, body: dict | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.status, json.loads(payload.decode("utf-8"))
        return response.status, {"bytes": len(payload), "content_type": content_type}


def _login(base_url: str, email: str, password: str) -> str:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "auth/login/")
    _, payload = _json_request(url, method="POST", body={"email": email, "password": password})
    token = payload.get("access") or payload.get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but no access token was returned.")
    return token


def check_frontend_build(dist: Path) -> dict:
    index = dist / "index.html"
    assets = dist / "assets"
    if not index.exists():
        raise RuntimeError(f"Missing frontend build entry: {index}")
    if not assets.exists() or not any(assets.iterdir()):
        raise RuntimeError(f"Missing frontend build assets: {assets}")
    return {
        "check": "frontend_build_artifacts",
        "status": "pass",
        "index": str(index),
        "asset_count": sum(1 for _ in assets.iterdir()),
    }


def check_api(base_url: str, token: str) -> list[dict]:
    results = []
    api_root = base_url.rstrip("/") + "/"
    for name, method, path in DEFAULT_ENDPOINTS:
        url = urllib.parse.urljoin(api_root, path.lstrip("/"))
        status, payload = _json_request(url, method=method, token=token)
        if status >= 400:
            raise RuntimeError(f"{name} returned HTTP {status}")
        results.append({
            "check": name,
            "status": "pass",
            "http_status": status,
            "payload_summary": sorted(payload.keys())[:8] if isinstance(payload, dict) else type(payload).__name__,
        })
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run KnowPilot V8 release smoke checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1/")
    parser.add_argument("--frontend-dist", default="frontend/dist")
    parser.add_argument("--token", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--check-build-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        results = [check_frontend_build(Path(args.frontend_dist))]
        if not args.check_build_only:
            token = args.token or _login(args.base_url, args.email, args.password)
            results.extend(check_api(args.base_url, token))
        print(json.dumps({"status": "pass", "results": results}, indent=2))
        return 0
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
