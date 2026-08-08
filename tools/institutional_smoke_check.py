"""Institutional non-production smoke checks.

This script is for a deployed rehearsal environment, not CI-generated mock
identity. Protected checks require a real institutional access token supplied
out-of-band by the operator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SmokeResult:
    name: str
    status: Status
    detail: str


def _https_url(value: str, label: str) -> SmokeResult:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return SmokeResult(label, Status.FAIL, f"{label} must be an HTTPS URL.")
    return SmokeResult(label, Status.PASS, f"{label} is HTTPS.")


def _get_json(url: str, *, token: str | None = None, timeout: int = 15) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get(url, headers=headers, timeout=timeout)
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:500]
    return response.status_code, body


def run_smoke(frontend_url: str, api_base_url: str, token: str | None) -> list[SmokeResult]:
    results = [_https_url(frontend_url, "frontend_url"), _https_url(api_base_url, "api_base_url")]
    if any(result.status == Status.FAIL for result in results):
        return results

    try:
        response = requests.get(frontend_url, timeout=15)
        results.append(
            SmokeResult(
                "frontend_reachable",
                Status.PASS if response.status_code < 500 else Status.FAIL,
                f"Frontend returned HTTP {response.status_code}.",
            )
        )
    except requests.RequestException as exc:
        results.append(SmokeResult("frontend_reachable", Status.FAIL, f"Frontend request failed: {exc.__class__.__name__}."))

    for path, expected in (("/health/live", 200), ("/health/ready", 200)):
        try:
            status_code, _body = _get_json(urljoin(api_base_url.rstrip("/") + "/", path.lstrip("/")))
            results.append(
                SmokeResult(
                    path,
                    Status.PASS if status_code == expected else Status.FAIL,
                    f"{path} returned HTTP {status_code}.",
                )
            )
        except requests.RequestException as exc:
            results.append(SmokeResult(path, Status.FAIL, f"{path} failed: {exc.__class__.__name__}."))

    if not token:
        results.append(
            SmokeResult(
                "institutional_oidc_login",
                Status.BLOCKED,
                "Provide a real institutional access token with --access-token or INSTITUTIONAL_SMOKE_ACCESS_TOKEN.",
            )
        )
        return results

    protected_paths = [
        "/api/v1/session/capabilities",
        "/api/v1/subject/current-positions",
        "/api/v1/subject/information",
        "/api/v1/decision-reviews",
    ]
    for path in protected_paths:
        try:
            status_code, _body = _get_json(urljoin(api_base_url.rstrip("/") + "/", path.lstrip("/")), token=token)
            results.append(
                SmokeResult(
                    path,
                    Status.PASS if status_code == 200 else Status.FAIL,
                    f"{path} returned HTTP {status_code}.",
                )
            )
        except requests.RequestException as exc:
            results.append(SmokeResult(path, Status.FAIL, f"{path} failed: {exc.__class__.__name__}."))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run institutional deployment smoke checks with a real institutional token.")
    parser.add_argument("--frontend-url", default=os.environ.get("INSTITUTIONAL_SMOKE_FRONTEND_URL", ""))
    parser.add_argument("--api-base-url", default=os.environ.get("INSTITUTIONAL_SMOKE_API_BASE_URL", ""))
    parser.add_argument("--access-token", default=os.environ.get("INSTITUTIONAL_SMOKE_ACCESS_TOKEN", ""))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.frontend_url or not args.api_base_url:
        print("INSTITUTIONAL_SMOKE_FRONTEND_URL and INSTITUTIONAL_SMOKE_API_BASE_URL are required.", file=sys.stderr)
        return 2

    results = run_smoke(args.frontend_url.strip(), args.api_base_url.strip(), args.access_token.strip() or None)
    failed = any(result.status == Status.FAIL for result in results)
    blocked = any(result.status == Status.BLOCKED for result in results)
    if args.json:
        print(json.dumps({"results": [asdict(result) for result in results]}, indent=2))
    else:
        for result in results:
            print(f"[{result.status.value.upper()}] {result.name}: {result.detail}")
    if failed:
        return 1
    if blocked:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
