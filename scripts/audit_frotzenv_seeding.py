#!/usr/bin/env python3
"""Field-level screen: which indexed `FrotzEnv` call sites pass an explicit seed?

The methods note's prevalence audit is a hand-verified code read of a named set
of systems: for each, whether an explicit engine seed actually reaches the
engine. This script is the wider screen that sits beside that audit rather than
enlarging it — GitHub code search for `FrotzEnv`, then a classification of every
`FrotzEnv(...)` call site in the fetched files, by whether an explicit engine
seed is passed. It answers a different question, what the rate looks like across
public code, and it involves no model: every verdict is a regex over fetched
source, so the classification is deterministic and auditable.

**This is a screening instrument, not evidence on its own.** GitHub code search is
not a census: it indexes a subset, ranks rather than enumerates, caps results, and
returns a *different* set from one run to the next. Anything that lands in the
paper must be hand-verified, exactly as the named systems in the note already
were. Report it as "of the M indexed call sites we could classify", never as "of
all Jericho users".

What a verdict does not settle: SEEDED means an explicit `seed=` reached the
constructor, not that it *varies* — a hardcoded `seed=42` is one fixed tape and
still scores SEEDED. (`seed=0` and `seed=None` are the exception; they re-bind
the walkthrough seed through the falsy-coalescing path, so they score FROZEN.) A
seed threaded in from a caller several frames up is invisible to a file-local
scan, which is what UNKNOWN and the post-hoc downgrade route to a human. Call
sites and repositories are separate denominators; see `tally_rows`.

Because the search is not reproducible, the artifact is written to be
*re-verifiable instead*: every classified row records the repository's head
commit at fetch time, a permalink pinned to that commit, and the SHA-256 of the
file content the verdict was computed from. A reader cannot reproduce the search,
but can re-fetch the exact bytes behind every row and check the call.

Requires: `gh` CLI, authenticated (`gh auth status`). Stdlib only otherwise.

Usage:
    python3 scripts/audit_frotzenv_seeding.py --limit 100
    python3 scripts/audit_frotzenv_seeding.py --limit 100 --json data/audit_frotzenv_seeding_2026-08-13.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize

# The bare identifier, not `FrotzEnv(`: GitHub code search
# tokenizes on punctuation, so including the paren does not narrow the result set
# and risks dropping hits. Matching the actual constructor call is `classify_file`'s
# job, against fetched file text, where a real regex applies. The artifact records
# this query verbatim so the two stages cannot be confused for one.
QUERY = "FrotzEnv"

# `FrotzEnv(...)` up to the closing paren on the same line. Good enough for a
# screen: multi-line constructor calls are reported as UNKNOWN, not guessed at.
CALL_RE = re.compile(r"FrotzEnv\s*\(([^)]*)\)")
SEED_KW_RE = re.compile(r"\bseed\s*=")
# `seed=None` / `seed=0` re-bind the walkthrough seed via `seed or bindings[...]`,
# so they are not a fix: they select the same frozen tape a bare call would.
SEED_FALSY_RE = re.compile(r"\bseed\s*=\s*(None|0)\b")
# A seed applied AFTER construction is invisible to a constructor-only scan:
# `env.seed(n)`, or a wrapper's `reset(seed=...)`. TextQuests seeds exactly this
# way (`if seed: self.seed(seed)`), so scoring a bare `FrotzEnv(rom)` as FROZEN
# in such a file is a false positive. Presence anywhere in the file downgrades a
# would-be FROZEN verdict to UNKNOWN, for hand-checking.
POST_HOC_SEED_RE = re.compile(r"\.seed\s*\(|\breset\s*\([^)]*\bseed\s*=")

V_FROZEN_NONE = "FROZEN (no seed argument)"
V_FROZEN_FALSY = "FROZEN (seed=None/0 re-binds walkthrough seed)"
V_SEEDED = "SEEDED (explicit seed argument)"
V_UNKNOWN_POSITIONAL = "UNKNOWN (positional args — hand-check)"
V_UNKNOWN_MULTILINE = "UNKNOWN (multi-line call)"
V_UNKNOWN_POST_HOC = "UNKNOWN (seed applied elsewhere in file — hand-check)"

# Jericho itself is the library, not a user of it. This repository is skipped too:
# the note's own artifact repo turning up in the note's own field survey would be
# circular, and it will be publicly searchable once released.
SKIP_REPOS = {"microsoft/jericho", "abahgat/jericho-seed-confound"}
SKIP_PATH_RE = re.compile(r"\.(md|rst|txt|ipynb)$|/docs?/|/tests?/", re.I)


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def gh_json(args: list[str]) -> object:
    """Run a gh command that emits JSON; exit with a readable error if it fails."""
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"gh failed: {' '.join(args)}\n{proc.stderr.strip()}")
    return json.loads(proc.stdout or "[]")


def gh_version() -> str:
    code, out = run(["gh", "--version"])
    return out.splitlines()[0].strip() if code == 0 and out else "unknown"


def search_call_sites(limit: int) -> tuple[list[tuple[str, str]], int]:
    """Deduped (repo, path) pairs, plus the raw hit count before filtering.

    The raw count is what shows whether GitHub's cap was reached — i.e.
    whether this is a truncated sample rather than everything indexed.
    """
    hits = gh_json([
        "gh", "search", "code", QUERY, "--language", "python",
        "--limit", str(limit), "--json", "repository,path",
    ])
    seen, out = set(), []
    for h in hits:
        repo, path = h["repository"]["nameWithOwner"], h["path"]
        if repo in SKIP_REPOS or SKIP_PATH_RE.search(path) or (repo, path) in seen:
            continue
        seen.add((repo, path))
        out.append((repo, path))
    return out, len(hits)


def repo_metadata(repo: str, cache: dict) -> dict:
    """Head commit, fork status and visibility, cached per repo.

    The head commit is what makes a row re-verifiable: `contents` fetches the
    default branch, which moves. Recording the commit turns each row into a
    permalink that shows a later reader the same bytes we classified.

    Visibility is checked because `gh search code` searches whatever the token
    can see, so an authenticated run surfaces private repositories the runner
    happens to have access to. Such a row is unverifiable for every other reader
    — the permalink 404s — and publishing it would leak private source, so
    `main` drops those repositories before fetching any content.
    """
    if repo not in cache:
        info = gh_json(["gh", "api", f"repos/{repo}",
                        "--jq", "{fork: .fork, private: .private, default_branch: .default_branch}"])
        branch = info.get("default_branch") or "HEAD"
        try:
            sha = gh_json(["gh", "api", f"repos/{repo}/commits/{branch}", "--jq", "{sha: .sha}"])["sha"]
        except SystemExit:
            sha = None
        cache[repo] = {"is_fork": bool(info.get("fork")),
                       "is_private": bool(info.get("private")),
                       "default_branch": branch, "head_commit": sha}
    return cache[repo]


def fetch(repo: str, path: str) -> str | None:
    code, out = run(["gh", "api", f"repos/{repo}/contents/{path}",
                     "-H", "Accept: application/vnd.github.raw"])
    return out if code == 0 else None


def mask_noncode(source: str) -> list[str]:
    """Blank comment and string-literal text, preserving line and column layout.

    A `FrotzEnv(` inside a comment or a docstring is not a call site. Without
    this, a commented-out construction scores as a live one, and prose describing
    the constructor scores as a frozen call.

    String *contents* are blanked in place rather than removed, so the structure
    of a real call survives: `FrotzEnv("zork1.z5", seed=1)` still reads as seeded.
    Files that do not tokenize — Python 2, and truncated files, both present in
    this corpus — fall back to blanking from `#` to end of line.
    """
    lines = source.splitlines()
    masked = list(lines)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                continue
            (r1, c1), (r2, c2) = tok.start, tok.end
            for row in range(r1, min(r2, len(masked)) + 1):
                text = masked[row - 1]
                a = c1 if row == r1 else 0
                b = c2 if row == r2 else len(text)
                masked[row - 1] = text[:a] + " " * (b - a) + text[b:]
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        masked = [re.sub(r"#.*$", lambda m: " " * len(m.group(0)), ln) for ln in lines]
    return masked


def classify_file(source: str) -> list[dict]:
    """Classify every FrotzEnv call site in one file.

    Pure function of the file text — no network, no globals — so the thing that
    actually makes the claim is unit-testable. See test_audit_classifier.py.

    Verdicts are computed against comment- and string-masked text, while `code`
    reports the line as it really appears, so a reader checking a permalink sees
    what was there.
    """
    lines = source.splitlines()
    masked = mask_noncode(source)
    post_hoc = bool(POST_HOC_SEED_RE.search("\n".join(masked)))
    out = []
    for lineno, (line, scan) in enumerate(zip(lines, masked), 1):
        m = CALL_RE.search(scan)
        if not m:
            # A constructor call broken across lines: flag for hand-checking
            # rather than silently dropping it.
            if "FrotzEnv" in scan and "(" in scan and ")" not in scan:
                out.append({"line": lineno, "verdict": V_UNKNOWN_MULTILINE,
                            "code": line.strip()})
            continue
        args = m.group(1)
        if SEED_FALSY_RE.search(args):
            verdict = V_FROZEN_FALSY
        elif SEED_KW_RE.search(args):
            verdict = V_SEEDED
        elif args.count(",") >= 1:
            verdict = V_UNKNOWN_POSITIONAL
        elif post_hoc:
            verdict = V_UNKNOWN_POST_HOC
        else:
            verdict = V_FROZEN_NONE
        out.append({"line": lineno, "verdict": verdict, "code": line.strip()})
    return out


def bucket(verdict: str) -> str:
    return verdict.split(" ")[0]


def tally_rows(rows: list[dict]) -> dict:
    """Both denominators, kept separate on purpose.

    A single repository with fifteen call sites contributes fifteen to the
    call-site tally. "N% of call sites" is not "N% of projects", and conflating
    them is the easiest way for this screen to overstate its reach.
    """
    by_call_site: dict[str, int] = {}
    for r in rows:
        b = bucket(r["verdict"])
        by_call_site[b] = by_call_site.get(b, 0) + 1

    repos: dict[str, set] = {}
    for r in rows:
        repos.setdefault(r["repo"], set()).add(bucket(r["verdict"]))
    by_repo = {
        "repos_total": len(repos),
        "repos_with_any_frozen": sum(1 for b in repos.values() if "FROZEN" in b),
        "repos_all_seeded": sum(1 for b in repos.values() if b == {"SEEDED"}),
    }
    return {"by_call_site": by_call_site, "by_repo": by_repo,
            "distinct_file_contents": len({r["content_sha256"] for r in rows}),
            "call_sites_in_forks": sum(1 for r in rows if r["is_fork"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=100,
                    help="max code-search hits to request (GitHub caps at 100)")
    ap.add_argument("--json", metavar="PATH", help="write the full result set here")
    args = ap.parse_args()

    started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    sites, raw_hits = search_call_sites(args.limit)
    limit_reached = raw_hits >= args.limit
    print(f"{raw_hits} raw hit(s); {len(sites)} file(s) after dedupe/filtering"
          f"{' — LIMIT REACHED, truncated sample' if limit_reached else ''}\n",
          file=sys.stderr)

    meta_cache: dict = {}
    rows, fetch_failures, nonpublic = [], [], []
    for repo, path in sites:
        # Visibility first, so private content is never fetched, hashed or quoted.
        meta = repo_metadata(repo, meta_cache)
        if meta["is_private"]:
            nonpublic.append({"repo": repo, "path": path})
            continue
        src = fetch(repo, path)
        if src is None:
            fetch_failures.append({"repo": repo, "path": path})
            continue
        content_sha = hashlib.sha256(src.encode("utf-8", "replace")).hexdigest()
        for call in classify_file(src):
            commit = meta["head_commit"]
            rows.append({
                "repo": repo,
                "path": path,
                "is_fork": meta["is_fork"],
                "head_commit": commit,
                "permalink": (f"https://github.com/{repo}/blob/{commit}/{path}"
                              f"#L{call['line']}") if commit else None,
                "content_sha256": content_sha,
                **call,
            })
            print(f"{call['verdict']:<52} {repo}/{path}:{call['line']}")

    tally = tally_rows(rows)
    total = sum(tally["by_call_site"].values())
    # Two different file counts: fetched files vs files that yielded a call site.
    # A file can match the search (an import, a comment) yet contain nothing
    # classifiable, so conflating the two overstates the denominator.
    files_with_sites = len({(r["repo"], r["path"]) for r in rows})
    # Files actually fetched, i.e. excluding the ones skipped as non-public;
    # counting those would inflate the denominator by files nobody can read.
    files_fetched = len(sites) - len(nonpublic)
    print(f"\n--- {total} classified call site(s) in {files_with_sites} of "
          f"{files_fetched} fetched file(s), "
          f"{tally['by_repo']['repos_total']} repo(s) ---")
    if nonpublic:
        print(f"  skipped {len(nonpublic)} file(s) in "
              f"{len({n['repo'] for n in nonpublic})} non-public repo(s)")
    for b, n in sorted(tally["by_call_site"].items(), key=lambda kv: -kv[1]):
        print(f"  {b:<10} {n:>4}  ({n / total:.0%})" if total else f"  {b}: {n}")
    print(f"  repos with >=1 FROZEN call site: "
          f"{tally['by_repo']['repos_with_any_frozen']}/{tally['by_repo']['repos_total']}")
    print(f"  distinct file contents: {tally['distinct_file_contents']} "
          f"(lower than the file count means vendored/forked copies)")
    if limit_reached:
        print("  NOTE: search hit the result cap — this is a truncated sample.")
    print("\nScreening only — hand-verify every call site before it enters the paper.")

    if args.json:
        artifact = {
            # Provenance first: enough to tell a changed finding from a changed
            # environment, mirroring the demo artifacts in data/.
            "generated_utc": started,
            "query": QUERY,
            "language": "python",
            "limit": args.limit,
            "raw_hits": raw_hits,
            "limit_reached": limit_reached,
            "gh_version": gh_version(),
            "skip_repos": sorted(SKIP_REPOS),
            "skip_path_pattern": SKIP_PATH_RE.pattern,
            # Files fetched, excluding those skipped for being non-public: this
            # is the denominator a reader can actually re-verify against.
            "files_considered": len(sites) - len(nonpublic),
            # Counts, not identities: naming a repository the search reached but
            # a reader cannot would disclose private paths to no useful end.
            "nonpublic_skipped": {
                "files": len(nonpublic),
                "repos": len({n["repo"] for n in nonpublic}),
            },
            "fetch_failures": fetch_failures,
            "tally": tally,
            "results": rows,
        }
        with open(args.json, "w") as fh:
            json.dump(artifact, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
