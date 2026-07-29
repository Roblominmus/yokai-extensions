#!/usr/bin/env python3
"""
ci_selfheal.py — CI driver for the self-heal loop. Wraps the *proven* heal.py
orchestrator with the extra concerns CI needs, without duplicating heal.py's
detect->groq->validate->gate->retry-or-revert logic.

Per configured source it:
  1. SYNC   the repo's real src/en/<name>/ .kt into the parse-harness source set
            (import_source.sh) so the harness authoritatively tests CURRENT code.
  2. HEAL   run heal.py --source <id> --file <harness copy of main .kt> ...
            heal.py detects (harness), and only if BROKEN does it window live
            evidence, ask Groq, structurally validate, and GATE each candidate on
            the harness. It NEVER keeps a fix that fails the gate.
              - exit 0 + no diff  -> HEALTHY (already parsed)
              - exit 0 + a diff   -> HEALED  (gate-confirmed repair in harness copy)
              - exit 1            -> ESCALATE (could not heal in N attempts; reverted)
  3. PROMOTE on HEALED: copy the gate-confirmed harness .kt files back into
            src/en/<name>/ so a `git commit` on main triggers build-and-publish.
            Only ever promotes code the live harness confirmed works.
  4. ESCALATE on failure: `gh issue create` describing the break for a human.

Prints a clear per-source summary and, if $GITHUB_OUTPUT is set, writes
  healed=<csv> escalated=<csv> healthy=<csv> any_committed=true|false
for the workflow to consume.

Never prints GROQ_API_KEY or any secret.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "parse-harness"
# repo root is the parent of self-healing/ (this dir lives at <repo>/self-healing/)
REPO = HERE.parent

# --- source registry -------------------------------------------------------
# For each source: the harness id (Runner.kt), the repo module dir, the harness
# package leaf that heal.py edits, the main .kt filename, the parse type, and the
# live URL + windowing keyword used ONLY when a repair is actually needed.
SOURCES = [
    {
        "id": "mangapill",
        "name": "mangapill",
        "repo_dir": "src/en/mangapill",
        "leaf": "eu/kanade/tachiyomi/extension/en/mangapill",
        "main_kt": "MangaPill.kt",
        "type": "html",
        "url": "https://mangapill.com/",
        "keyword": "Trending",
    },
    {
        "id": "weebcentral",
        "name": "weebcentral",
        "repo_dir": "src/en/weebcentral",
        "leaf": "eu/kanade/tachiyomi/extension/en/weebcentral",
        "main_kt": "WeebCentral.kt",
        "type": "html",
        "url": "https://weebcentral.com/",
        "keyword": "article",
    },
]


def harness_leaf_dir(src: dict) -> Path:
    return HARNESS / "src/main/kotlin" / src["leaf"]


def repo_leaf_dir(src: dict) -> Path:
    # repo layout: src/en/<name>/src/<leaf>/
    return REPO / src["repo_dir"] / "src" / src["leaf"]


def sync_repo_into_harness(src: dict) -> None:
    """Copy the repo's current .kt for this source into the harness source set."""
    module_dir = REPO / src["repo_dir"]
    r = subprocess.run(
        ["bash", str(HARNESS / "import_source.sh"), str(module_dir)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[sync] import_source.sh failed for {src['name']}:\n{r.stdout}\n{r.stderr}")
        raise SystemExit(3)
    print(f"[sync] {src['name']}: repo -> harness")


def run_heal(src: dict) -> tuple[int, str]:
    main_kt = harness_leaf_dir(src) / src["main_kt"]
    cmd = [
        sys.executable, str(HERE / "heal.py"),
        "--source", src["id"],
        "--file", str(main_kt),
        "--type", src["type"],
        "--url", src["url"],
        "--keyword", src["keyword"],
        "--max-retries", "3",
    ]
    # heal.py reads GROQ_API_KEY from the environment (or self-healing/.env, which is
    # absent in CI). Never echo the value.
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))
    out = r.stdout + r.stderr
    print(out)
    return r.returncode, out


def harness_changed(src: dict) -> bool:
    """Did heal.py leave a gate-confirmed edit in the harness copy vs the repo?"""
    for kt in harness_leaf_dir(src).glob("*.kt"):
        repo_kt = repo_leaf_dir(src) / kt.name
        if not repo_kt.exists():
            return True
        if kt.read_text() != repo_kt.read_text():
            return True
    return False


def promote(src: dict) -> list[str]:
    """Copy gate-confirmed harness .kt back into the repo module. Returns changed files."""
    changed: list[str] = []
    dst_dir = repo_leaf_dir(src)
    for kt in harness_leaf_dir(src).glob("*.kt"):
        dst = dst_dir / kt.name
        if not dst.exists() or dst.read_text() != kt.read_text():
            shutil.copy(kt, dst)
            changed.append(str(dst.relative_to(REPO)))
    print(f"[promote] {src['name']}: {changed}")
    return changed


def escalate(src: dict, log: str) -> None:
    """Open a GitHub issue so a human can look. Never commits a broken fix."""
    title = f"[self-heal] {src['name']} parse is broken and could not be auto-repaired"
    tail = "\n".join(log.splitlines()[-40:])
    body = (
        f"The scheduled self-heal run detected that **{src['name']}** "
        f"(`{src['repo_dir']}`) no longer parses live data, and the automated "
        f"Groq repair loop could not produce a fix that passes the live "
        f"parse-harness gate within 3 attempts.\n\n"
        f"No change was committed (the harness gate rejected every candidate), so "
        f"the extension is unchanged on `main`.\n\n"
        f"**Source id:** `{src['id']}`  \n"
        f"**Live URL checked:** {src['url']}\n\n"
        f"<details><summary>heal.py log tail</summary>\n\n```\n{tail}\n```\n</details>\n\n"
        f"Please inspect the source's selectors against the current site DOM."
    )
    if not shutil.which("gh"):
        print("[escalate] gh not available; would have opened issue:\n" + title)
        return
    r = subprocess.run(
        ["gh", "issue", "create", "--title", title, "--body", body,
         "--label", "self-heal,broken-source"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    # labels may not exist in a fresh fork; retry without them so escalation still works
    if r.returncode != 0 and "label" in (r.stdout + r.stderr).lower():
        r = subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body],
            capture_output=True, text=True, cwd=str(REPO),
        )
    print(f"[escalate] {src['name']}: {r.stdout.strip()}{r.stderr.strip()}")


def set_output(**kw) -> None:
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if not gh_out:
        return
    with open(gh_out, "a") as f:
        for k, v in kw.items():
            f.write(f"{k}={v}\n")


def main() -> int:
    only = sys.argv[1:]  # optional: restrict to given source names
    sources = [s for s in SOURCES if not only or s["name"] in only or s["id"] in only]

    healthy: list[str] = []
    healed: list[dict] = []      # {name, files}
    escalated: list[str] = []

    for src in sources:
        print(f"\n{'='*60}\n=== {src['name']} ===\n{'='*60}")
        sync_repo_into_harness(src)
        rc, log = run_heal(src)

        if rc == 0 and not harness_changed(src):
            print(f"[result] {src['name']}: HEALTHY")
            healthy.append(src["name"])
        elif rc == 0 and harness_changed(src):
            files = promote(src)
            print(f"[result] {src['name']}: HEALED (gate-confirmed) -> {files}")
            healed.append({"name": src["name"], "files": files})
        else:
            print(f"[result] {src['name']}: ESCALATE (heal failed, reverted, no commit)")
            escalate(src, log)
            escalated.append(src["name"])

    # -------- summary --------
    print(f"\n{'#'*60}\n# SELF-HEAL SUMMARY\n{'#'*60}")
    print(f"  HEALTHY   ({len(healthy)}): {', '.join(healthy) or '-'}")
    print(f"  HEALED    ({len(healed)}): "
          f"{', '.join(h['name'] for h in healed) or '-'}")
    print(f"  ESCALATED ({len(escalated)}): {', '.join(escalated) or '-'}")

    healed_names = [h["name"] for h in healed]
    all_healed_files = [f for h in healed for f in h["files"]]
    set_output(
        healthy=",".join(healthy),
        healed=",".join(healed_names),
        escalated=",".join(escalated),
        healed_files=" ".join(all_healed_files),
        any_committed="true" if healed_names else "false",
        commit_msg=(
            "self-heal: repair " + ", ".join(healed_names) +
            " (live parse-harness gate confirmed)"
        ) if healed_names else "",
    )
    # Exit 0 always: escalation is a normal, expected outcome that must NOT fail the
    # job (the workflow already opened an issue). A non-zero here would just make the
    # run red for a condition we deliberately handled. Real infra errors raise above.
    return 0


if __name__ == "__main__":
    sys.exit(main())
