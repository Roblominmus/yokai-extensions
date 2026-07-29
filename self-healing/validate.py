#!/usr/bin/env python3
"""
validate.py — safety gate before an AI candidate is allowed anywhere near a commit.

This is the part the Gemini plan hand-waved and it's 80% of the real work: an LLM
will happily emit confident, broken, or truncated Kotlin. Nothing here trusts the
model. Two layers:

  Layer 1 (this script, cheap, no SDK): STRUCTURAL guards on the candidate vs the
    original — catches the common LLM failure modes (truncation, renamed class,
    changed package/id, dropped versionCode bump, unbalanced braces).

  Layer 2 (CI, authoritative): `./gradlew :extensions:...:assembleRelease` must
    compile the candidate, and a source-run test must call the source's
    popular/latest/chapter/page parse against the live page and assert non-empty
    output. Only if BOTH pass does the pipeline open a PR. See self-healing.yml.

Exit 0 = candidate passes structural gate; non-zero = reject.
"""
from __future__ import annotations

import argparse
import re
import sys

CHECKS: list[str] = []


def guard(cond: bool, ok_msg: str, fail_msg: str) -> bool:
    CHECKS.append(("PASS " + ok_msg) if cond else ("FAIL " + fail_msg))
    return cond


def line_value(text: str, pattern: str):
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--min-ratio", type=float, default=0.6,
                    help="candidate must be at least this fraction of original length (anti-truncation)")
    args = ap.parse_args()

    original = open(args.original).read()
    candidate = open(args.candidate).read()

    ok = True

    # 1. anti-truncation
    ratio = len(candidate) / max(len(original), 1)
    ok &= guard(ratio >= args.min_ratio,
                f"length ratio {ratio:.2f} >= {args.min_ratio}",
                f"candidate is only {ratio:.2f} of original — likely truncated")

    # 2. package must be unchanged
    op = line_value(original, r"^package\s+([\w.]+)")
    cp = line_value(candidate, r"^package\s+([\w.]+)")
    ok &= guard(op == cp and op is not None, f"package unchanged ({op})",
                f"package changed {op} -> {cp}")

    # 3. class name must be preserved (declaration may span multiple lines, so
    #    match the name only — robust against `class Foo(\n  ...\n) : Bar {`)
    oc = line_value(original, r"\bclass\s+(\w+)")
    cc = line_value(candidate, r"\bclass\s+(\w+)")
    ok &= guard(oc == cc and oc is not None, f"class name unchanged ({oc})",
                f"class name changed {oc} -> {cc}")

    # 4. brace / paren balance
    ok &= guard(candidate.count("{") == candidate.count("}"),
                "braces balanced", "unbalanced braces")
    ok &= guard(candidate.count("(") == candidate.count(")"),
                "parens balanced", "unbalanced parens")

    # 5. versionCode should be bumped (build .gradle usually, but warn if present here)
    ovc = line_value(original, r"versionCode\s*=?\s*(\d+)")
    cvc = line_value(candidate, r"versionCode\s*=?\s*(\d+)")
    if ovc is not None:
        ok &= guard(cvc is not None and int(cvc) > int(ovc),
                    f"versionCode bumped {ovc} -> {cvc}",
                    f"versionCode not bumped (still {cvc}) — do it in build.gradle if not here")

    # 6. must actually differ from original
    ok &= guard(candidate.strip() != original.strip(),
                "candidate differs from original", "candidate is identical to original (no fix)")

    print("\n".join("  " + c for c in CHECKS))
    print("\nRESULT:", "PASS (structural) — proceed to Gradle build" if ok else "REJECT")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
