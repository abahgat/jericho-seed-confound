"""Guard the prevalence screen's artifact, and the one figure quoted from it.

The artifact is dated and not reproducible, so its counts stay in `tally` — which
a re-run updates on its own — instead of being copied into prose. One figure is
quoted, in the root README, and checked here as a whole sentence: clause-by-clause
patterns would let a partial rewrite check less than the full claim.

Stdlib + pytest; no network, no `gh`.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

HERE = pathlib.Path(__file__).parent
DATA = HERE / "data"
ARTIFACTS = sorted(DATA.glob("audit_frotzenv_seeding_*.json"))

#: The one sentence that copies counts out of this artifact. Matched whole, so a
#: partial rewrite fails instead of quietly checking less.
HEADLINE_RE = re.compile(
    r"of \*\*(\d+) classified call sites\*\* across (\d+) repositories, "
    r"\*\*(\d+) \((\d+)%\) pass no engine seed\*\*")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def _prose(path: pathlib.Path) -> str:
    """File text with whitespace collapsed, so patterns survive rewrapping."""
    return " ".join(path.read_text().split())


def _described_run() -> tuple[pathlib.Path, dict]:
    """The artifact the root README names — a reference, not a transcription."""
    names = re.findall(r"data/(audit_frotzenv_seeding_[\d-]+\.json)",
                       _prose(HERE / "README.md"))
    assert names, "README.md names no audit artifact"
    assert len(set(names)) == 1, f"README.md names several: {sorted(set(names))}"
    path = DATA / names[0]
    assert path.exists(), f"README.md points at {names[0]}, which is not committed"
    return path, _load(path)


def test_artifacts_exist():
    """The note cites this file; a missing artifact means an uncitable claim."""
    assert ARTIFACTS, "no data/audit_frotzenv_seeding_*.json committed"


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_artifact_is_self_describing(path):
    """Enough provenance to tell a changed finding from a changed search."""
    a = _load(path)
    for field in ("generated_utc", "query", "language", "limit", "raw_hits",
                  "limit_reached", "gh_version", "skip_repos", "skip_path_pattern",
                  "files_considered", "nonpublic_skipped", "fetch_failures",
                  "tally", "results"):
        assert field in a, f"{path.name}: missing provenance field {field!r}"


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_tally_is_consistent_with_the_rows(path):
    """The tally must be arithmetic on `results`, not a parallel record of it."""
    a = _load(path)
    rows, tally = a["results"], a["tally"]
    buckets: dict[str, int] = {}
    for r in rows:
        b = r["verdict"].split(" ")[0]
        buckets[b] = buckets.get(b, 0) + 1
    assert tally["by_call_site"] == buckets
    assert sum(tally["by_call_site"].values()) == len(rows)

    by_repo: dict[str, set] = {}
    for r in rows:
        by_repo.setdefault(r["repo"], set()).add(r["verdict"].split(" ")[0])
    assert tally["by_repo"]["repos_total"] == len(by_repo)
    assert tally["by_repo"]["repos_with_any_frozen"] == sum(
        1 for b in by_repo.values() if "FROZEN" in b)
    assert tally["by_repo"]["repos_all_seeded"] == sum(
        1 for b in by_repo.values() if b == {"SEEDED"})
    assert tally["distinct_file_contents"] == len({r["content_sha256"] for r in rows})
    assert tally["call_sites_in_forks"] == sum(1 for r in rows if r["is_fork"])


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_every_row_is_re_verifiable(path):
    """The screen's answer to being unreproducible: each row pins its own bytes."""
    a = _load(path)
    for r in a["results"]:
        assert r["head_commit"], f"{r['repo']}/{r['path']}: no head commit"
        assert r["permalink"] == (f"https://github.com/{r['repo']}/blob/"
                                  f"{r['head_commit']}/{r['path']}#L{r['line']}")
        assert re.fullmatch(r"[0-9a-f]{64}", r["content_sha256"])


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_files_considered_excludes_the_non_public_drop(path):
    """The denominator counts files actually fetched, never the dropped ones."""
    a = _load(path)
    files_with_sites = len({(r["repo"], r["path"]) for r in a["results"]})
    assert files_with_sites <= a["files_considered"]
    assert a["nonpublic_skipped"]["repos"] <= a["nonpublic_skipped"]["files"]


def test_readme_headline_figure_matches_the_artifact():
    """The single transcription, checked against the file it came from."""
    _, a = _described_run()
    tally = a["tally"]
    total = sum(tally["by_call_site"].values())
    frozen = tally["by_call_site"]["FROZEN"]

    quoted = HEADLINE_RE.findall(_prose(HERE / "README.md"))
    assert len(quoted) == 1, (
        f"expected one headline figure in README.md, found {len(quoted)}")
    sites, repos, n_frozen, pct = (int(g) for g in quoted[0])
    assert sites == total
    assert repos == tally["by_repo"]["repos_total"]
    assert n_frozen == frozen
    assert pct == round(frozen / total * 100)


def test_cap_claim_matches_the_artifact():
    """The README calls this a truncated sample; the artifact must agree."""
    _, a = _described_run()
    text = _prose(HERE / "README.md")
    if "result cap" in text or "limit_reached: true" in text:
        assert a["limit_reached"] is True, "README calls it truncated; artifact does not"


def test_no_document_restates_the_breakdown():
    """Counts belong in `tally`; prose copies do not update themselves."""
    for name in ("README.md", "data/README.md"):
        text = _prose(HERE / name)
        for pattern in (r"\(\d+%\) pass an explicit one",
                        r"\(\d+%\) need a hand check",
                        r"\d+ of the \d+ fetched files",
                        r"\d+ of the \d+ repositories hold"):
            assert not re.search(pattern, text), f"{name} restates {pattern!r}"

    # A first-match pattern reads the original and stops, so a stray count further
    # down a document would pass as agreement.
    assert not re.search(r"\(\d+%\) pass no engine seed", _prose(DATA / "README.md")), (
        "data/README.md states a FROZEN rate; the figure belongs in the root README")
