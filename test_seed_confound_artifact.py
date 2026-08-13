"""Guard the paper's headline table against silent drift.

The methods note reports its numbers *from* the committed artifacts in `data/`
rather than from prose, so the paper's claim and the data cannot diverge
unnoticed. These tests re-derive the table from those files and assert the three
claims the note actually makes:

  1. the unseeded default collapses N runs to ONE world state (SD = 0),
  2. an explicit `seed=0` resolves to the SAME walkthrough seed (the falsy-
     coalescing trap), and
  3. a randomized positive seed restores variation.

Plus the version-invariance claim: the artifacts for two engine versions must be
identical in every field except `jericho_version`; these tests are the only check
of that claim.

Stdlib only; needs no engine (it reads committed JSON), so it runs in the fast CI
suite. Regenerate the artifacts with `python seed_confound_demo.py --rom PATH --out`.
"""
from __future__ import annotations

import json
import pathlib

import pytest

DATA = pathlib.Path(__file__).parent / "data"
WALKTHROUGH_SEED = 12  # Zork I's bindings seed — the frozen tape the note is about
ARTIFACTS = sorted(DATA.glob("seed_confound_demo_jericho-*.json"))


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def _condition(artifact: dict, needle: str) -> dict:
    matches = [c for c in artifact["conditions"] if needle in c["condition"]]
    assert len(matches) == 1, f"expected exactly one {needle!r} condition, got {len(matches)}"
    return matches[0]


def test_artifacts_exist():
    """The note cites these files; a missing artifact means an uncitable claim."""
    assert ARTIFACTS, (
        "no data/seed_confound_demo_jericho-*.json — regenerate with "
        "`python seed_confound_demo.py --rom PATH --out`"
    )


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_artifact_is_self_describing(path):
    """Enough provenance to tell a changed finding from a changed environment."""
    a = _load(path)
    for field in ("jericho_version", "rom", "rom_sha256", "meta_seed", "actions",
                  "action_list", "runs_per_condition", "conditions"):
        assert field in a, f"{path.name}: missing provenance field {field!r}"
    assert a["actions"] == len(a["action_list"])
    assert len(a["conditions"]) == 3
    for cond in a["conditions"]:
        assert cond["n"] == a["runs_per_condition"]
        assert len(cond["runs"]) == cond["n"]


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_default_collapses_to_one_realization(path):
    """Claim 1: N 'independent' runs are N copies of one draw."""
    cond = _condition(_load(path), "default")
    assert cond["distinct_world_states"] == 1
    assert cond["score_sd"] == 0.0
    assert cond["resolved_seeds"] == [WALKTHROUGH_SEED]


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_seed_zero_rebinds_the_walkthrough_seed(path):
    """Claim 2: `seed=0` re-binds the walkthrough seed, via `seed or bindings[…]`."""
    cond = _condition(_load(path), "seed=0")
    assert cond["resolved_seeds"] == [WALKTHROUGH_SEED]
    assert cond["distinct_world_states"] == 1
    assert cond["score_sd"] == 0.0


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_randomized_seeds_recover_a_distribution(path):
    """Claim 3: same actions, real spread — the spread comes from the engine RNG."""
    a = _load(path)
    cond = _condition(a, "randomized")
    assert cond["distinct_world_states"] > 1
    assert cond["score_sd"] > 0.0
    # The fix's lower bound of 1 is not arbitrary: a 0 would re-bind the walkthrough
    # seed through the same falsy-coalescing path.
    assert all(s >= 1 for s in cond["resolved_seeds"])
    assert WALKTHROUGH_SEED not in cond["resolved_seeds"]


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_every_condition_ran_the_same_number_of_times(path):
    """Equal N per condition, over a non-empty action list.

    Note what this does NOT check. The demonstration depends on the action
    sequence being identical across conditions — but the artifact stores
    a single top-level `action_list` shared by all three, so behaviour-fixity is
    guaranteed by the schema rather than re-derivable from the file. If the demo
    ever grows per-condition action lists, assert their equality here."""
    a = _load(path)
    assert a["actions"] > 0
    assert len({c["n"] for c in a["conditions"]}) == 1
    assert all(c["n"] == a["runs_per_condition"] for c in a["conditions"])


def test_version_invariance():
    """The note says the result is invariant across jericho 3.2.0–3.3.1. With two
    artifacts present, that is checkable rather than asserted: they must agree in
    every field, per-run world-state hashes included, except the version itself."""
    if len(ARTIFACTS) < 2:
        pytest.skip("version-invariance needs artifacts from two engine versions")
    first, *rest = [_load(p) for p in ARTIFACTS]
    for other in rest:
        assert first["jericho_version"] != other["jericho_version"]
        differing = {k for k in set(first) | set(other) if first.get(k) != other.get(k)}
        assert differing == {"jericho_version"}, (
            f"artifacts differ beyond the engine version in {sorted(differing)} — "
            "either the engine changed the RNG path or the demo is not deterministic"
        )
