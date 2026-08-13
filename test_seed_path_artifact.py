"""Guard the paper's path-sensitivity claims against silent drift.

The methods note claims that, under the frozen walkthrough tape, (1) padding
with RNG-quiet actions leaves a downstream fight byte-identical, while (2) a
single extra RNG-consuming action flips it. Those claims were previously
verified only in prose; `seed_path_demo.py` records them
in `data/seed_path_demo_jericho-*.json`, and these tests re-derive them from the
committed file so the paper and its evidence cannot diverge.

The design is a minimal pair: the SAME padding action string
(`look`) is used in both padded conditions — only where it lands (RNG-quiet
above-ground vs the Troll Room, where each turn consumes a combat draw) differs.

Stdlib only; needs no engine. Regenerate with
`python seed_path_demo.py --rom PATH --out`.
"""
from __future__ import annotations

import json
import pathlib

import pytest

DATA = pathlib.Path(__file__).parent / "data"
WALKTHROUGH_SEED = 12  # Zork I's bindings seed — the frozen tape under test
ARTIFACTS = sorted(DATA.glob("seed_path_demo_jericho-*.json"))


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def _condition(artifact: dict, needle: str) -> dict:
    matches = [c for c in artifact["conditions"] if needle in c["condition"]]
    assert len(matches) == 1, f"expected exactly one {needle!r} condition, got {len(matches)}"
    return matches[0]


def test_artifacts_exist():
    """The note cites these files; a missing artifact means an uncitable claim."""
    assert ARTIFACTS, (
        "no data/seed_path_demo_jericho-*.json — regenerate with "
        "`python seed_path_demo.py --rom PATH --out`"
    )


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_artifact_is_self_describing(path):
    a = _load(path)
    for field in ("jericho_version", "rom", "rom_sha256", "kill_action", "pad_action",
                  "quiet_insert_index", "rng_insert_index", "base_action_list",
                  "conditions"):
        assert field in a, f"{path.name}: missing provenance field {field!r}"
    assert len(a["conditions"]) == 4


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_all_conditions_run_on_the_frozen_walkthrough_tape(path):
    """Every condition is UNSEEDED — the path, not the seed, is the variable."""
    a = _load(path)
    assert all(c["resolved_seed"] == WALKTHROUGH_SEED for c in a["conditions"])


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_quiet_padding_is_byte_identical_to_baseline(path):
    """Claim 1: RNG-quiet padding leaves the tape untouched — outcome, score and
    world-state hash all match baseline, at padding depth 1 and 3."""
    a = _load(path)
    base = _condition(a, "baseline")
    for needle in ("quiet padding x1", "quiet padding x3"):
        c = _condition(a, needle)
        assert c["matches_baseline"] is True
        assert c["state_hash"] == base["state_hash"]
        assert c["score"] == base["score"]
        assert c["fight_obs"] == base["fight_obs"]
        assert c["n_actions"] > base["n_actions"]  # longer path, same outcome


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_one_rng_consuming_action_flips_the_outcome(path):
    """Claim 2: ONE extra RNG-consuming turn shifts the frozen tape — the same
    fight resolves differently."""
    a = _load(path)
    base = _condition(a, "baseline")
    c = _condition(a, "rng padding x1")
    assert c["matches_baseline"] is False
    assert c["fight_obs"] != base["fight_obs"]
    assert c["state_hash"] != base["state_hash"]


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_minimal_pair_uses_the_same_padding_action(path):
    """Identical action string, different RNG consumption. If the demo ever pads
    with different actions, it no longer isolates the path axis."""
    a = _load(path)
    assert a["pad_action"].lower() == "look"
    quiet = _condition(a, "quiet padding x1")
    rng = _condition(a, "rng padding x1")
    assert quiet["n_actions"] == rng["n_actions"]  # same length, opposite outcome


def test_version_invariance():
    """With artifacts from two engine versions, the result must agree in every
    field except the version itself (mirrors test_seed_confound_artifact.py)."""
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
