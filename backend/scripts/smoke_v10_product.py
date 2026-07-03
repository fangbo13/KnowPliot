"""V10 product closure smoke checks with safe JSON output."""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def request(url, token="", *, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as response:
        content = response.read()
        return {
            "status": response.status,
            "content_type": response.headers.get("Content-Type", ""),
            "body": content,
        }


def check_build(dist):
    index = dist / "index.html"
    assets = dist / "assets"
    if not index.is_file() or not assets.is_dir() or not any(assets.iterdir()):
        raise RuntimeError("Frontend production artifacts are incomplete.")
    return {"check": "frontend_build", "status": "pass"}


def login(root, email, password):
    response = request(
        urllib.parse.urljoin(root, "auth/token/"),
        method="POST",
        payload={"email": email, "password": password},
    )
    data = json.loads(response["body"])
    token = data.get("access")
    if not token:
        raise RuntimeError("Login response did not contain an access token.")
    return token


def check_api(root, token, session_id):
    paths = [
        ("health", "admin/health/"),
        ("quality_evaluations", "admin/quality/evaluations/"),
        ("template_catalog", "templates/?sort=recommended"),
        (
            "session_markdown_export",
            f"chat/sessions/{session_id}/export/?format=markdown",
        ),
    ]
    results = []
    for name, path in paths:
        response = request(urllib.parse.urljoin(root, path), token)
        if response["status"] >= 400 or not response["body"]:
            raise RuntimeError(f"{name} failed.")
        results.append(
            {
                "check": name,
                "status": "pass",
                "http_status": response["status"],
                "content_type": response["content_type"],
            }
        )
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run KnowPilot V10 product smoke.")
    parser.add_argument("--frontend-dist", default="frontend/dist")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1/")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--check-build-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        results = [check_build(Path(args.frontend_dist))]
        if not args.check_build_only:
            if not all([args.email, args.password, args.session_id]):
                raise RuntimeError("API smoke requires email, password, and session-id.")
            root = args.base_url.rstrip("/") + "/"
            results.extend(
                check_api(
                    root,
                    login(root, args.email, args.password),
                    args.session_id,
                )
            )
        print(json.dumps({"status": "pass", "results": results}, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "error": exc.__class__.__name__,
                    "detail": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
