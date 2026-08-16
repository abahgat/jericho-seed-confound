"""Test the sentences a reader actually reads.

`reading.py` turns measured DVs into the demos' printed conclusion. That makes it,
like the audit classifier, a place where a claim gets made, so it is pinned here.
Two things are under test:

  1. Fed the committed artifacts, it produces the note's reading. This is what
     stops the prose and the evidence from drifting apart: if a regenerated
     artifact stopped showing the collapse, these tests fail instead of the demo
     printing the previous conclusion.

  2. Fed a post-fix run, it reports the confound as ABSENT. No committed artifact
     exercises that branch — jericho <= 3.3.1 always collapses — so without a
     synthetic case the reporting added for the fixed engine would itself be
     untested.

Stdlib + pytest; no engine, no ROM, no network.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import reading

DATA = pathlib.Path(__file__).parent / "data"
SEED_ARTIFACTS = sorted(DATA.glob("seed_confound_demo_jericho-*.json"))
PATH_ARTIFACTS = sorted(DATA.glob("seed_path_demo_jericho-*.json"))


def _by_name(conditions, prefix):
    return next(c for c in conditions if c["condition"].startswith(prefix))


def _seed_axis(artifact):
    conditions = json.loads(artifact.read_text())["conditions"]
    return reading.describe_seed_axis(_by_name(conditions, "default"),
                                      _by_name(conditions, "explicit seed=0"),
                                      _by_name(conditions, "randomized"))


# --------------------------------------------------------------------------
# The seed axis, against the committed evidence
# --------------------------------------------------------------------------

def test_seed_artifacts_exist():
    assert SEED_ARTIFACTS, "no seed-axis artifacts to read"


@pytest.mark.parametrize("artifact", SEED_ARTIFACTS, ids=lambda p: p.stem)
def test_committed_run_reads_as_a_collapse(artifact):
    text = " ".join(_seed_axis(artifact))
    assert "collapses" in text and "ONE realization" in text
    assert "ABSENT" not in text, (
        "a committed artifact read as post-fix — either the artifact was "
        "regenerated against a patched engine, or the reading logic broke"
    )


@pytest.mark.parametrize("artifact", SEED_ARTIFACTS, ids=lambda p: p.stem)
def test_committed_run_names_the_falsy_trap(artifact):
    """seed=0 and the default landing on one seed is the trap, not a coincidence."""
    text = " ".join(_seed_axis(artifact))
    assert "falsy-coalescing" in text
    assert "SAME engine seed" in text


@pytest.mark.parametrize("artifact", SEED_ARTIFACTS, ids=lambda p: p.stem)
def test_committed_run_credits_randomization(artifact):
    assert "restores variation" in " ".join(_seed_axis(artifact))


# --------------------------------------------------------------------------
# The seed axis on a post-fix engine, which no artifact can supply
# --------------------------------------------------------------------------

def test_post_fix_run_reports_the_confound_absent():
    """The branch that matters on an engine carrying microsoft/jericho#88.

    Numbers modelled on a real run against a patched build: the unseeded default
    draws a fresh seed per episode (recorded as -1) and spreads across states, so
    the demo must NOT claim a collapse.
    """
    default = {"n": 4, "score_sd": 12.56, "distinct_world_states": 4,
               "resolved_seeds": [-1]}
    seed_zero = {"n": 4, "score_sd": 0.0, "distinct_world_states": 1,
                 "resolved_seeds": [0]}
    randomized = {"n": 4, "score_sd": 12.56, "distinct_world_states": 4,
                  "resolved_seeds": [1, 2, 3, 4]}
    text = " ".join(reading.describe_seed_axis(default, seed_zero, randomized))
    assert "does NOT bind the walkthrough seed" in text
    assert "ABSENT" in text
    assert "collapses" not in text
    # seed=0 is still a frozen tape, but no longer the walkthrough one, so the
    # trap must not be named here.
    assert "still freezes the tape" in text
    assert "falsy-coalescing" not in text


def test_post_fix_run_does_not_claim_one_realization():
    """Regression guard for the bug this module was written to prevent: prose
    asserting a collapse next to numbers that show four distinct states."""
    default = {"n": 12, "score_sd": 9.9, "distinct_world_states": 11,
               "resolved_seeds": [-1]}
    seed_zero = {"n": 12, "score_sd": 4.2, "distinct_world_states": 7,
                 "resolved_seeds": [0]}
    randomized = {"n": 12, "score_sd": 9.9, "distinct_world_states": 11,
                  "resolved_seeds": [5, 6]}
    text = " ".join(reading.describe_seed_axis(default, seed_zero, randomized))
    assert "ONE realization" not in text
    assert "did not freeze the tape" in text


# --------------------------------------------------------------------------
# The path axis
# --------------------------------------------------------------------------

def test_path_artifacts_exist():
    assert PATH_ARTIFACTS, "no path-axis artifacts to read"


@pytest.mark.parametrize("artifact", PATH_ARTIFACTS, ids=lambda p: p.stem)
def test_committed_path_run_reads_as_one_tape_and_a_flip(artifact):
    a = json.loads(artifact.read_text())
    text = " ".join(reading.describe_path_axis(
        a["conditions"], pad_action=a["pad_action"],
        quiet_index=a["quiet_insert_index"], rng_index=a["rng_insert_index"]))
    assert "one frozen tape" in text
    assert "quiet padding is inert" in text
    assert "one RNG-consuming action flips it" in text
    assert "PREMISE FAILED" not in text
    assert "unexpected" not in text


def test_path_run_on_varying_seeds_reports_a_failed_premise():
    """The held-fixed seed is this demo's control. If it varies, report that
    rather than comparing paths across different tapes."""
    conditions = [
        {"condition": "baseline", "resolved_seed": 111, "score": 40,
         "matches_baseline": True},
        {"condition": "quiet padding x1", "resolved_seed": 222, "score": 40,
         "matches_baseline": True},
        {"condition": "quiet padding x3", "resolved_seed": 333, "score": 35,
         "matches_baseline": False},
        {"condition": "rng padding x1", "resolved_seed": 444, "score": 30,
         "matches_baseline": False},
    ]
    text = " ".join(reading.describe_path_axis(
        conditions, pad_action="look", quiet_index=6, rng_index=27))
    assert "PREMISE FAILED" in text
    assert "quiet padding is inert" not in text
    assert "flips it" not in text


@pytest.mark.parametrize("sentinel", [-1, None])
def test_path_run_treats_a_sentinel_seed_as_no_tape(sentinel):
    """The bug a live run against a patched engine actually exposed.

    On jericho 4.0 the unseeded constructor draws a fresh seed per episode but
    records the sentinel -1, so all four conditions report the *same* resolved
    value while sitting on four different tapes. An equality check alone therefore
    concluded "one frozen tape" and went on to compare paths across seeds. A
    sentinel names no tape and must fail the premise.
    """
    conditions = [
        {"condition": "baseline", "resolved_seed": sentinel, "score": 30,
         "matches_baseline": True},
        {"condition": "quiet padding x1", "resolved_seed": sentinel, "score": 40,
         "matches_baseline": False},
        {"condition": "quiet padding x3", "resolved_seed": sentinel, "score": 40,
         "matches_baseline": False},
        {"condition": "rng padding x1", "resolved_seed": sentinel, "score": 40,
         "matches_baseline": False},
    ]
    text = " ".join(reading.describe_path_axis(
        conditions, pad_action="look", quiet_index=6, rng_index=27))
    assert "PREMISE FAILED" in text
    assert "one frozen tape" not in text
    assert "flips it" not in text


def test_seed_axis_does_not_call_two_sentinels_a_shared_tape():
    """Two conditions both reporting -1 agree on 'random', not on a tape."""
    frozen_looking = {"n": 3, "score_sd": 0.0, "distinct_world_states": 1,
                      "resolved_seeds": [-1]}
    text = " ".join(reading.describe_seed_axis(
        frozen_looking, frozen_looking,
        {"n": 3, "score_sd": 5.0, "distinct_world_states": 3,
         "resolved_seeds": [7, 8, 9]}))
    assert "falsy-coalescing" not in text
    assert "SAME engine seed" not in text


def test_path_run_flags_quiet_padding_that_is_not_quiet():
    """If the chosen index stops being RNG-quiet, that is a broken demo, not a
    finding — and it must not be reported as the note's result."""
    conditions = [
        {"condition": "baseline", "resolved_seed": 12, "score": 40,
         "matches_baseline": True},
        {"condition": "quiet padding x1", "resolved_seed": 12, "score": 30,
         "matches_baseline": False},
        {"condition": "quiet padding x3", "resolved_seed": 12, "score": 40,
         "matches_baseline": True},
        {"condition": "rng padding x1", "resolved_seed": 12, "score": 30,
         "matches_baseline": False},
    ]
    text = " ".join(reading.describe_path_axis(
        conditions, pad_action="look", quiet_index=6, rng_index=27))
    assert "unexpected: quiet padding changed the outcome" in text
    assert "quiet padding x1" in text
    assert "quiet padding is inert" not in text
