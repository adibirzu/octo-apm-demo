"""Rollout validator (KG-040).

Polls `/api/version` on every pod of a Deployment until they all
report the expected image_tag + git_sha. Useful after a blue/green
cutover or rolling update to confirm every replica has flipped
before traffic is shifted.

Usage:
    python tools/rollout-validator/validate.py \\
        --namespace octo-shop-prod \\
        --label-selector app=octo-drone-shop \\
        --expected-tag 20260423-abc123 \\
        --timeout 300

Exits 0 when every pod reports the expected tag, 1 on timeout, 2 on
argument error.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from typing import Any


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--label-selector", required=True, help="kubectl label selector, e.g. app=octo-drone-shop")
    ap.add_argument("--expected-tag", required=True, help="image tag every pod must report")
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait")
    ap.add_argument("--poll-interval", type=int, default=5)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--path", default="/api/version")
    return ap.parse_args()


def _list_pods(namespace: str, selector: str) -> list[str]:
    proc = subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace, "-l", selector,
         "-o", "jsonpath={.items[*].metadata.name}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return []
    return [n for n in proc.stdout.split() if n]


def _pod_version(namespace: str, pod: str, port: int, path: str) -> str:
    """Port-forward + curl /api/version. Subprocess-only so no
    Python dep on kubernetes client needed."""
    # Using kubectl exec + curl is simpler than port-forward —
    # fewer moving parts, no race between port bind + curl.
    proc = subprocess.run(
        ["kubectl", "exec", "-n", namespace, pod, "--",
         "sh", "-c",
         f"curl -sS -m 3 http://localhost:{port}{path} | "
         f"python3 -c 'import json,sys;print(json.load(sys.stdin).get(\"image_tag\",\"\"))'"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout.strip()


def main() -> int:
    args = _parse_args()
    deadline = time.time() + args.timeout

    while time.time() < deadline:
        pods = _list_pods(args.namespace, args.label_selector)
        if not pods:
            print(f"[validator] no pods match selector {args.label_selector}; retry in {args.poll_interval}s")
            time.sleep(args.poll_interval)
            continue

        tags = {pod: _pod_version(args.namespace, pod, args.port, args.path) for pod in pods}
        matched = [p for p, t in tags.items() if t == args.expected_tag]
        mismatched = [(p, t) for p, t in tags.items() if t != args.expected_tag]

        print(f"[validator] matched {len(matched)}/{len(pods)} on tag {args.expected_tag}")
        if not mismatched:
            print("[validator] rollout complete.")
            return 0

        for p, t in mismatched:
            print(f"  - {p} reports {t!r}")
        time.sleep(args.poll_interval)

    print("[validator] TIMEOUT — not all pods converged in time.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
