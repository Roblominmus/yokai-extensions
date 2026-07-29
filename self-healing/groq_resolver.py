#!/usr/bin/env python3
"""
groq_resolver.py — propose a repair for a broken extension source using Groq.

Design principles (learned the hard way from the Gemini draft):
  1. It NEVER overwrites the original file and NEVER commits. It writes a
     *candidate* next to the original. Promotion happens only after validate.py
     (and, in CI, a real Gradle build) confirms the fix.
  2. The prompt is SOURCE-TYPE AWARE. "Rewrite the CSS selector" is meaningless
     for a JSON-API source (MangaFire, MangaDex, AllAnime). For those we ask for
     DTO field / endpoint / query-param corrections instead.
  3. It only runs for AI-repairable verdicts (PARSE_LAYOUT). SERVER / CLOUDFLARE
     / AUTH_TOKEN are refused with an explanation — no selector edit can fix them.

Zero third-party deps: talks to Groq's OpenAI-compatible endpoint over urllib.

Usage:
    export GROQ_API_KEY=...
    python3 groq_resolver.py --file path/to/Source.kt --type html \
        --evidence evidence.txt --verdict PARSE_LAYOUT [--model llama-3.3-70b-versatile]
    # --dry-run prints the prompt and exits (no key needed) for inspection/testing
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

REFUSE = {
    "SERVER": "Remote server 5xx — nothing in the extension code can fix this. Retry later.",
    "CLOUDFLARE": "Cloudflare challenge — this is a network/TLS problem, fix it in the app's "
                  "CloudflareInterceptor / User-Agent, not in the source parser.",
    "AUTH_TOKEN": "App-level auth/token rejection — the site now requires a token its JS computes. "
                  "This needs reverse-engineering the token scheme, not a selector edit.",
    "UNREACHABLE": "Host unreachable — DNS/timeout/connection. Not a parser problem.",
}

SYSTEM = (
    "You are a senior Kotlin engineer maintaining Tachiyomi/Mihon manga source "
    "extensions. Make the MINIMAL change that fixes the break. Edit ONLY the "
    "selector(s) that are actually broken (matching zero nodes). Do NOT touch "
    "selectors or helper functions that still work — helper functions like "
    "`*FromElement` are SHARED by popular/latest/search, so changing one affects all "
    "three; only edit a shared helper if the evidence proves it is broken everywhere. "
    "Never change package names, class names, ids, or versionCode. Output the COMPLETE "
    "corrected Kotlin file in a single ```kotlin fenced block and NOTHING else."
)

HTML_TASK = (
    "This is an HTML-scraping source (JSoup, ParsedHttpSource). The site's DOM "
    "changed so one or more `select(...)` / `selectFirst(...)` CSS selectors now "
    "match nothing. Using the live HTML evidence below, rewrite ONLY the broken "
    "CSS selectors so they again extract the same logical fields (title, url, "
    "cover, chapter list, page images)."
)

JSON_TASK = (
    "This is a JSON-API source (kotlinx.serialization DTOs). The API's JSON schema "
    "or endpoint changed, so deserialization or field access now yields empty "
    "results. Using the live JSON evidence below, correct ONLY the affected "
    "@SerialName field mappings, DTO shape, endpoint path, or query parameters so "
    "the same logical fields are populated again."
)


def build_prompt(kotlin_code: str, evidence: str, src_type: str, verdict_detail: str,
                 max_evidence: int = 60000) -> str:
    task = HTML_TASK if src_type == "html" else JSON_TASK
    ev = evidence[:max_evidence]
    fence = "html" if src_type == "html" else "json"
    return (
        f"{task}\n\n"
        f"Detector finding: {verdict_detail}\n\n"
        f"### Current (broken) Kotlin source\n```kotlin\n{kotlin_code}\n```\n\n"
        f"### Live response evidence (truncated)\n```{fence}\n{ev}\n```\n\n"
        f"Return the complete corrected Kotlin file now."
    )


def call_groq(prompt: str, model: str, api_key: str) -> str:
    payload = json.dumps({
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }).encode()
    req = urllib.request.Request(
        GROQ_URL, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Groq's API is behind Cloudflare; the default Python-urllib UA trips a
            # 1010 fingerprint ban, so present a normal browser UA.
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise SystemExit(f"Groq API {e.code}: {body[:800]}")
    return data["choices"][0]["message"]["content"]


def extract_kotlin(text: str) -> str | None:
    m = re.search(r"```(?:kotlin)?\s*\n(.*?)```", text, re.DOTALL)
    return m.group(1).rstrip() + "\n" if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="path to the broken .kt source")
    ap.add_argument("--type", choices=["html", "json"], required=True)
    ap.add_argument("--evidence", required=True, help="file with live HTML/JSON evidence")
    ap.add_argument("--verdict", default="PARSE_LAYOUT")
    ap.add_argument("--verdict-detail", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-evidence", type=int, default=60000,
                    help="chars of response evidence to include (raise if the target markup is deep in the page)")
    ap.add_argument("--dry-run", action="store_true", help="print prompt and exit")
    args = ap.parse_args()

    if args.verdict in REFUSE:
        print(f"REFUSING to run resolver for verdict={args.verdict}:\n  {REFUSE[args.verdict]}")
        sys.exit(2)

    with open(args.file) as f:
        kotlin_code = f.read()
    with open(args.evidence) as f:
        evidence = f.read()

    prompt = build_prompt(kotlin_code, evidence, args.type, args.verdict_detail, args.max_evidence)

    if args.dry_run:
        print("=== SYSTEM ===\n" + SYSTEM + "\n\n=== USER PROMPT ===\n" + prompt)
        return

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not set (use --dry-run to inspect the prompt)", file=sys.stderr)
        sys.exit(1)

    raw = call_groq(prompt, args.model, api_key)
    fixed = extract_kotlin(raw)
    if not fixed:
        print("ERROR: model did not return a kotlin code block. Raw output:\n" + raw[:1000],
              file=sys.stderr)
        sys.exit(1)

    candidate = args.file + ".candidate"
    with open(candidate, "w") as f:
        f.write(fixed)

    diff = difflib.unified_diff(
        kotlin_code.splitlines(keepends=True), fixed.splitlines(keepends=True),
        fromfile=args.file, tofile=candidate,
    )
    sys.stdout.writelines(diff)
    print(f"\n\nCandidate written to {candidate}")
    print("NOT committed. Run validate.py / Gradle build before promoting.")


if __name__ == "__main__":
    main()
