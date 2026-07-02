"""V9 operations smoke checks with safe JSON failure output."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_CHECKS = [
    ("health", "GET", "/admin/health/"),
    ("admin_metrics", "GET", "/admin/metrics/"),
    ("quality_report", "GET", "/admin/reports/knowledge-quality/"),
    ("export_jobs", "GET", "/admin/reports/export-jobs/"),
    ("notification_feed", "GET", "/notifications/"),
    ("review_queue", "GET", "/admin/quality/feedback/"),
]


def _request(url: str, token: str):
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            payload = json.loads(body.decode("utf-8"))
            summary = sorted(payload.keys())[:8] if isinstance(payload, dict) else type(payload).__name__
        else:
            summary = {"bytes": len(body), "content_type": content_type}
        return {"http_status": response.status, "payload_summary": summary}


def check_frontend_build(dist: Path):
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


def check_api(base_url: str, token: str):
    if not token:
        raise RuntimeError("API smoke requires --token or --check-build-only.")
    root = base_url.rstrip("/") + "/"
    results = []
    for name, _method, path in API_CHECKS:
        url = urllib.parse.urljoin(root, path.lstrip("/"))
        result = _request(url, token)
        if result["http_status"] >= 400:
            raise RuntimeError(f"{name} returned HTTP {result['http_status']}")
        results.append({"check": name, "status": "pass", **result})
    return results


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run KnowPilot V9 operations smoke checks.")
    parser.add_argument("--frontend-dist", default="frontend/dist")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1/")
    parser.add_argument("--token", default="")
    parser.add_argument("--check-build-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        results = [check_frontend_build(Path(args.frontend_dist))]
        if not args.check_build_only:
            results.extend(check_api(args.base_url, args.token))
        print(json.dumps({"status": "pass", "results": results}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "fail", "error": exc.__class__.__name__, "detail": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
