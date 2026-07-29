#!/usr/bin/env python3
"""
detector.py — output-shape health checker for manga extension sources.

Why this exists
---------------
The naive approach ("ping the site, check the HTTP status") MISSES the most
common real breakage: the site returns 200 OK but the layout/schema changed, so
the extension parses *nothing*. This detector fetches each source's key
endpoints and asserts the RESPONSE SHAPE, then classifies any failure into one
of five classes so the pipeline knows whether an AI selector-repair can even
help.

Failure classes (see README):
    OK            - endpoint returned and the expected shape is present
    SERVER        - HTTP 5xx (remote server broken; not fixable by us)
    CLOUDFLARE    - 403/503 + cloudflare server + challenge markers
    AUTH_TOKEN    - app-level auth/token rejection (e.g. {"message":"..."} )
    PARSE_LAYOUT  - HTTP 200 but expected shape missing (THE AI-fixable case)
    UNREACHABLE   - DNS/timeout/connection error

Zero third-party deps for JSON sources (uses only the stdlib) so it runs in a
bare CI container without a pip step. HTML sources use lxml if available and
degrade to a clear "dependency needed" note otherwise.

Usage:
    python3 detector.py --config sources.json [--only mangadex,mangafire] [--report report.json]
Exit code is non-zero if any checked source is not OK (so CI can branch on it).
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

CLOUDFLARE_MARKERS = ("challenge-error", "cf-chl", "just a moment", "cf-mitigated", "__cf_chl")


@dataclass
class CheckResult:
    source: str
    check: str
    url: str
    status: int | None
    verdict: str                 # one of the failure classes
    fixable_by_ai: bool
    detail: str
    elapsed_s: float
    server_header: str = ""
    evidence: str = ""           # short body snippet, for the resolver's context


# --------------------------------------------------------------------------- #
# JSON path evaluation (tiny, dependency-free)
# --------------------------------------------------------------------------- #
def _resolve_path(obj, path: str):
    """Resolve a dotted path with [i] / [*] segments. Returns list of matches.

    Examples: "result"  "data.0.id"  "result[*].id"  "pagination.total"
    """
    tokens: list = []
    for seg in path.split("."):
        while "[" in seg:
            name, rest = seg.split("[", 1)
            if name:
                tokens.append(name)
            idx, seg = rest.split("]", 1)
            tokens.append(idx if idx == "*" else int(idx))
        if seg:
            tokens.append(seg)

    current = [obj]
    for tok in tokens:
        nxt = []
        for c in current:
            if tok == "*":
                if isinstance(c, list):
                    nxt.extend(c)
                elif isinstance(c, dict):
                    nxt.extend(c.values())
            elif isinstance(tok, int):
                if isinstance(c, list) and -len(c) <= tok < len(c):
                    nxt.append(c[tok])
            else:
                if isinstance(c, dict) and tok in c:
                    nxt.append(c[tok])
        current = nxt
    return current


def _non_empty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return len(value) > 0
    return True  # numbers/bools count as present


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
def fetch(url: str, headers: dict, timeout: int = 25):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=headers, method="GET")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read()
            return {
                "status": resp.status,
                "headers": {k.lower(): v for k, v in resp.headers.items()},
                "body": body,
                "elapsed": time.monotonic() - t0,
            }
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return {
            "status": e.code,
            "headers": {k.lower(): v for k, v in (e.headers or {}).items()},
            "body": body,
            "elapsed": time.monotonic() - t0,
        }
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, ConnectionError) as e:
        return {"status": None, "headers": {}, "body": b"", "elapsed": time.monotonic() - t0,
                "error": str(e)}


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def classify(source: str, check: dict, resp: dict, src_type: str) -> CheckResult:
    url = check["url"]
    name = check.get("name", "check")
    status = resp["status"]
    elapsed = round(resp["elapsed"], 3)
    server = resp["headers"].get("server", "")
    body = resp["body"]
    text = body[:2000].decode("utf-8", "replace")

    def mk(verdict, fixable, detail):
        return CheckResult(source, name, url, status, verdict, fixable, detail,
                           elapsed, server, text[:400])

    if status is None:
        return mk("UNREACHABLE", False, resp.get("error", "no response"))

    if status >= 500:
        return mk("SERVER", False, f"remote server returned {status}")

    if status in (403, 503):
        low = text.lower()
        if "cloudflare" in server.lower() and any(m in low for m in CLOUDFLARE_MARKERS):
            return mk("CLOUDFLARE", False, "cloudflare challenge page detected")
        # app-level auth rejection: valid JSON body with a message field
        try:
            j = json.loads(text)
            if isinstance(j, dict) and any(k in j for k in ("message", "error", "detail")):
                return mk("AUTH_TOKEN", False,
                          f"app-level rejection: {j.get('message') or j.get('error') or j.get('detail')}")
        except Exception:
            pass
        return mk("AUTH_TOKEN", False, f"{status} without cloudflare challenge (likely token/geo)")

    if status != check.get("expect_status", 200):
        return mk("PARSE_LAYOUT", src_type == "html", f"unexpected status {status}")

    # status == 200 -> validate shape
    if src_type == "json":
        try:
            data = json.loads(body)
        except Exception as e:
            return mk("PARSE_LAYOUT", False, f"expected JSON, got unparseable body: {e}")
        for path in check.get("non_empty", []):
            matches = _resolve_path(data, path)
            if not matches or not any(_non_empty(m) for m in matches):
                return mk("PARSE_LAYOUT", True,
                          f"json path '{path}' missing/empty -> schema drift")
        for path, minimum in check.get("min_items", {}).items():
            matches = _resolve_path(data, path)
            count = len(matches[0]) if (matches and isinstance(matches[0], (list, dict))) else len(matches)
            if count < minimum:
                return mk("PARSE_LAYOUT", True,
                          f"json path '{path}' has {count} items (< {minimum}) -> schema drift")
        return mk("OK", True, "json shape present")

    if src_type == "html":
        try:
            from lxml import html as lxml_html  # type: ignore
        except ImportError:
            return mk("PARSE_LAYOUT", True,
                      "html source needs lxml (pip install lxml) to validate selectors")
        try:
            tree = lxml_html.fromstring(body)
        except Exception as e:
            return mk("PARSE_LAYOUT", True, f"html parse failed: {e}")
        for css in check.get("selectors_nonempty", []):
            try:
                found = tree.cssselect(css)
            except Exception as e:
                return mk("PARSE_LAYOUT", True, f"bad selector '{css}': {e}")
            if not found:
                return mk("PARSE_LAYOUT", True,
                          f"selector '{css}' matched 0 nodes -> DOM changed")
        return mk("OK", True, "html selectors matched")

    return mk("PARSE_LAYOUT", False, f"unknown source type '{src_type}'")


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def run(config: dict, only: set[str] | None) -> list[CheckResult]:
    results: list[CheckResult] = []
    for src in config["sources"]:
        if only and src["id"] not in only:
            continue
        headers = {"User-Agent": src.get("user_agent", DEFAULT_UA), **src.get("headers", {})}
        for check in src["checks"]:
            resp = fetch(check["url"], headers, timeout=config.get("timeout", 25))
            results.append(classify(src["id"], check, resp, src["type"]))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="sources.json")
    ap.add_argument("--only", default="", help="comma-separated source ids")
    ap.add_argument("--report", default="", help="write JSON report to this path")
    args = ap.parse_args()

    with open(args.config) as f:
        config = json.load(f)
    only = {s for s in args.only.split(",") if s} or None

    results = run(config, only)

    broken = [r for r in results if r.verdict != "OK"]
    ai_fixable = [r for r in broken if r.fixable_by_ai]

    print(f"\n{'SOURCE':<14}{'CHECK':<10}{'STATUS':<7}{'VERDICT':<14}DETAIL")
    print("-" * 90)
    for r in results:
        flag = "" if r.verdict == "OK" else ("  <- AI-repairable" if r.fixable_by_ai else "  <- manual")
        print(f"{r.source:<14}{r.check:<10}{str(r.status):<7}{r.verdict:<14}{r.detail[:40]}{flag}")

    print("-" * 90)
    print(f"total={len(results)}  ok={len(results)-len(broken)}  broken={len(broken)}  "
          f"ai-repairable={len(ai_fixable)}")

    if args.report:
        with open(args.report, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"report written to {args.report}")

    # non-zero exit if anything broke, so CI can branch
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
