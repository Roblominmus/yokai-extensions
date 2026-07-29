#!/usr/bin/env python3
"""
heal.py — end-to-end self-healing orchestrator (the whole loop in one command).

    detect (JVM harness)  ->  capture windowed live evidence  ->  Groq repair
    (with accumulated failure feedback)  ->  structural validate  ->  promote
    ->  authoritative harness gate  ->  retry-with-feedback, or REVERT.

Guarantees it NEVER leaves a fix that fails the gate: on success it keeps the
candidate; on exhaustion it reverts to the pre-heal file. This is exactly the loop
that was proven by hand on MangaPill (3 Groq attempts; the gate rejected 2 bad
fixes before accepting the good one).

Example:
    set -a; . ./.env; set +a
    python3 heal.py --source mangapill \
        --file parse-harness/src/main/kotlin/eu/kanade/tachiyomi/extension/en/mangapill/MangaPill.kt \
        --type html --url https://mangapill.com/ --keyword Trending
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
HARNESS = HERE / "parse-harness"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def load_dotenv():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def run_harness(source_id: str) -> tuple[bool, str]:
    r = subprocess.run(
        ["./gradlew", "run", f"--args={source_id}", "--no-daemon", "--console=plain", "-q"],
        cwd=HARNESS, capture_output=True, text=True,
    )
    return r.returncode == 0, r.stdout + r.stderr


def fail_lines(out: str) -> str:
    return "\n".join(l for l in out.splitlines() if "FAIL" in l or "Exception" in l)[:800]


def fetch(url: str) -> str:
    # curl (not urllib) to dodge Cloudflare client-fingerprint bans
    r = subprocess.run(["curl", "-sS", "-m", "25", "-A", UA, "-H", f"Referer: {url}", url],
                       capture_output=True, text=True)
    return r.stdout


def window(html: str, keyword: str | None, before: int = 800, after: int = 11000) -> str:
    if not keyword:
        return html[:12000]
    i = html.find(keyword)
    return html[:12000] if i < 0 else html[max(0, i - before): i + after]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="source id registered in the harness Runner")
    ap.add_argument("--file", required=True, help="path to the source's .kt file")
    ap.add_argument("--type", choices=["html", "json"], required=True)
    ap.add_argument("--url", required=True, help="live URL to capture repair evidence from")
    ap.add_argument("--keyword", default="", help="window the evidence around this text")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--max-evidence", type=int, default=12000)
    args = ap.parse_args()

    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY not set (put it in self-healing/.env)")

    kt = Path(args.file)

    print(f"[detect] running harness on '{args.source}'...")
    ok, out = run_harness(args.source)
    if ok:
        print("[detect] source already parses — nothing to heal.")
        return 0
    print(f"[detect] BROKEN:\n{fail_lines(out)}")

    backup = kt.with_suffix(kt.suffix + ".prehealth")
    shutil.copy(kt, backup)

    print(f"[evidence] fetching {args.url}")
    ev = window(fetch(args.url), args.keyword or None)
    ev_path = HERE / "heal_evidence.html"
    ev_path.write_text(ev)
    print(f"[evidence] {len(ev)} bytes windowed around '{args.keyword or '(head)'}'")

    base_detail = (f"ONLY the {args.type} parse for source '{args.source}' is broken. "
                   "Make the minimal selector fix; do not touch working code or shared helpers.")
    feedback = ""

    for attempt in range(1, args.max_retries + 1):
        print(f"\n===== attempt {attempt}/{args.max_retries} =====")
        r = subprocess.run(
            [sys.executable, str(HERE / "groq_resolver.py"), "--file", str(kt), "--type", args.type,
             "--evidence", str(ev_path), "--verdict", "PARSE_LAYOUT",
             "--verdict-detail", base_detail + feedback, "--max-evidence", str(args.max_evidence)],
            capture_output=True, text=True,
        )
        cand = Path(str(kt) + ".candidate")
        if not cand.exists():
            print(f"[groq] no candidate: {r.stdout}{r.stderr}")
            feedback += "\nPrevious attempt produced no valid Kotlin block."
            continue

        v = subprocess.run(
            [sys.executable, str(HERE / "validate.py"), "--original", str(backup), "--candidate", str(cand)],
            capture_output=True, text=True,
        )
        if v.returncode != 0:
            print(f"[validate] structural REJECT:\n{v.stdout}")
            feedback += "\nPrevious candidate failed structural validation; keep the file complete and intact."
            cand.unlink(missing_ok=True)
            shutil.copy(backup, kt)
            continue
        print("[validate] structural PASS")

        shutil.copy(cand, kt)
        print("[gate] running harness on candidate...")
        ok, out = run_harness(args.source)
        if ok:
            print(f"[gate] PASS — healed on attempt {attempt}. Keeping fix.")
            cand.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
            return 0
        print(f"[gate] REJECT:\n{fail_lines(out)}")
        feedback += f"\nAttempt {attempt} was applied but FAILED the live parse gate:\n{fail_lines(out)}"
        if "NullPointerException" in out:
            # generic maintainer heuristic: NPE means the selector matched nodes that
            # lack the expected child fields (image/link/title) — it's too broad.
            feedback += ("\nThe NullPointerException means your selector matched nodes that are NOT "
                         "item cards (they lack the expected child image/link/title). Narrow it to "
                         "exactly the item cards and change nothing else.")
        shutil.copy(backup, kt)          # revert to broken for the next attempt
        cand.unlink(missing_ok=True)

    shutil.copy(backup, kt)              # exhausted: revert, never ship a bad fix
    backup.unlink(missing_ok=True)
    print(f"\n[done] could not heal '{args.source}' in {args.max_retries} attempts. "
          "Reverted — no broken fix shipped. Escalate to a human.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
