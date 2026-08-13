"""Turn a demo's measured DVs into the sentences a reader sees.

Kept apart from the demos, and stdlib-only, for two reasons.

First, testability. The printed summary is the claim a human actually reads, so it
is re-derived rather than asserted, as the audit classifier is in
`test_audit_classifier.py`. Living here, free of the `jericho` import, it can be
exercised against the committed artifacts in `data/` by a test suite that never
boots the engine. See `test_reading.py`.

Second, correctness across engine versions. The original demos ended with a hardcoded
"Reading:" paragraph asserting that the unseeded default collapses to one
realization. That is true of jericho <= 3.3.1 and false of any engine carrying the
upstream fix (microsoft/jericho#88), where the unseeded constructor is stochastic.
A demo that printed the old conclusion next to numbers contradicting it would
state a claim its own output disproves. So every sentence below is computed from
the run.
"""
from __future__ import annotations

#: Resolved-seed values that name no tape. Jericho uses -1 for "draw a fresh seed
#: per episode", and None means the engine exposed nothing. Neither is a tape
#: identifier, so equality between them means nothing: four episodes all
#: recording -1 ran on four *different* tapes.
STOCHASTIC_SENTINELS = (None, -1)


def _sortable(seeds):
    """Order a seed set for display, tolerating None."""
    return sorted(seeds, key=lambda s: (s is None, s if s is not None else 0))


def describe_seed_axis(default: dict, seed_zero: dict, randomized: dict) -> list[str]:
    """Describe a `seed_confound_demo` run from its three condition summaries.

    Each argument is one entry of the artifact's `conditions` list.
    """
    lines = []
    default_frozen = default["distinct_world_states"] == 1
    seed0_frozen = seed_zero["distinct_world_states"] == 1
    # The falsy-coalescing trap shows up as both conditions landing on one and the
    # same engine seed: `seed or bindings['seed']` turns an explicit 0 into 12.
    # A sentinel is excluded: two conditions both reporting -1 agree on "random",
    # which is the opposite of sharing a tape.
    shared_tape = (len(default["resolved_seeds"]) == 1
                   and default["resolved_seeds"] == seed_zero["resolved_seeds"]
                   and default["resolved_seeds"][0] not in STOCHASTIC_SENTINELS)

    if default_frozen:
        lines.append(
            f"the unseeded default collapses {default['n']} 'independent' runs to "
            f"ONE realization (SD={default['score_sd']:.2f}, "
            f"{default['distinct_world_states']} distinct world state) — an "
            f"'average over {default['n']} runs' here averages {default['n']} "
            "copies of a single draw.")
    else:
        lines.append(
            "this engine does NOT bind the walkthrough seed by default: the "
            f"unseeded condition produced {default['distinct_world_states']} "
            f"distinct world states (SD={default['score_sd']:.2f}) from resolved "
            f"seed(s) {default['resolved_seeds'][:6]}. The confound this demo "
            "characterizes is ABSENT here, so you are running a patched or "
            "post-fix engine, not the 3.2.0/3.3.1 behavior the note reports.")

    if seed0_frozen and shared_tape:
        lines.append(
            f"an explicit seed=0 resolves to the SAME engine seed "
            f"({default['resolved_seeds'][0]}) as the default — the "
            "falsy-coalescing trap, where `seed or bindings['seed']` rebinds the "
            "walkthrough seed instead of selecting tape 0.")
    elif seed0_frozen:
        lines.append(
            f"an explicit seed=0 still freezes the tape "
            f"({seed_zero['distinct_world_states']} distinct state, "
            f"SD={seed_zero['score_sd']:.2f}, resolved "
            f"{seed_zero['resolved_seeds'][:6]}); a hardcoded constant is a fixed "
            "tape whether or not the unseeded default is.")
    else:
        lines.append(
            f"an explicit seed=0 did not freeze the tape here "
            f"({seed_zero['distinct_world_states']} distinct states, resolved "
            f"{seed_zero['resolved_seeds'][:6]}).")

    verb = ("restores variation" if randomized["distinct_world_states"] > 1
            else "unexpectedly did NOT vary")
    lines.append(
        f"randomizing the seed {verb}: {randomized['distinct_world_states']} "
        f"distinct states (SD={randomized['score_sd']:.2f}), with behavior held "
        "identical by construction — so every difference above is engine RNG, not "
        "policy.")
    return lines


def describe_path_axis(conditions: list[dict], *, pad_action: str,
                       quiet_index: int, rng_index: int) -> list[str]:
    """Describe a `seed_path_demo` run from its four condition results."""
    baseline = next(c for c in conditions if c["condition"] == "baseline")
    quiet = [c for c in conditions if c["condition"].startswith("quiet")]
    rng = next(c for c in conditions if c["condition"].startswith("rng"))
    seeds = {c["resolved_seed"] for c in conditions}

    # The whole design holds the seed fixed to isolate the path axis. On an engine
    # that draws a fresh seed per episode that premise is gone, and every
    # comparison below would be confounded by the seed rather than by the path.
    if len(seeds) != 1:
        return [
            f"PREMISE FAILED: the conditions did not share one tape (resolved "
            f"seeds {_sortable(seeds)}). This demo isolates the path axis by "
            "holding the seed fixed, so a comparison across different tapes is "
            "confounded by the seed and shows nothing about paths. Run it against "
            "jericho <= 3.3.1, or pin the seed explicitly."]

    only = next(iter(seeds))
    if only in STOCHASTIC_SENTINELS:
        return [
            f"PREMISE FAILED: every condition reports resolved seed {only!r}, "
            "which is a 'draw a fresh seed' sentinel rather than a tape "
            f"identifier — so these {len(conditions)} runs sat on "
            f"{len(conditions)} different tapes, not one, and the outcome "
            "differences below are seed noise, not path sensitivity. You are on a "
            "patched or post-fix engine (microsoft/jericho#88); run against "
            "jericho <= 3.3.1, or pin the seed explicitly."]

    lines = [f"all {len(conditions)} conditions ran on one frozen tape "
             f"(resolved seed {only})."]

    if all(c["matches_baseline"] for c in quiet):
        lines.append(
            f"quiet padding is inert: {len(quiet)} condition(s) inserting "
            f"`{pad_action}` above ground (index {quiet_index}) leave the fight "
            "byte-identical to baseline — same world-state hash, score and "
            "observation — despite a longer action path.")
    else:
        broke = ", ".join(c["condition"] for c in quiet if not c["matches_baseline"])
        lines.append(
            f"unexpected: quiet padding changed the outcome ({broke}). Index "
            f"{quiet_index} may no longer be RNG-quiet for this game or engine.")

    if not rng["matches_baseline"]:
        lines.append(
            f"one RNG-consuming action flips it: the SAME `{pad_action}`, placed "
            f"inside the Troll Room (index {rng_index}), diverges from baseline "
            f"(score {rng['score']} vs {baseline['score']}). The action string is "
            "identical; only its RNG consumption differs — so exposure tracks "
            "RNG-consuming operations, not move count.")
    else:
        lines.append(
            f"unexpected: the RNG-consuming padding at index {rng_index} matched "
            "baseline, so this run does not demonstrate the path axis.")
    return lines
