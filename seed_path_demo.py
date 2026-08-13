#!/usr/bin/env python3
"""Path-sensitivity demonstration (the mechanism's second axis).

No model and no API calls. Companion to `seed_confound_demo.py`: that script shows the
*seed* axis (same actions, different seeds → different outcomes); this one shows
the *path* axis (same seed — the silent walkthrough default — different paths to
the same fight → the frozen tape does or does not shift, depending only on how
many RNG-consuming operations the detour adds).

The two claims:

  1. Under the default (walkthrough) seed, the fight outcome is invariant to
     padding with actions that consume no engine RNG ("quiet" padding).
  2. A single extra RNG-consuming action before the fight flips the outcome.

The minimal pair that isolates this: the SAME padding action — `look` — placed
above ground (no hostile NPC, no `@random` draw) leaves the troll fight
byte-identical to baseline, world-state hash included; placed inside the Troll
Room (where every turn consumes a combat draw for the troll's attack) it turns
the baseline's one-shot kill into a dodge. The padding *action string* is
identical; only its RNG consumption differs. This is why raw move-count is the
wrong exposure metric and RNG-consuming-operation count is the right one.

Conditions (all on the UNSEEDED default, i.e. the frozen walkthrough tape;
baseline is the walkthrough prefix through "Kill troll with sword"):

  baseline           the prefix as-is                       → one-shot kill
  quiet padding x1   +1 `look` above ground (index 6)       → identical outcome
  quiet padding x3   +3 `look` above ground (index 6)       → identical outcome
  rng padding x1     +1 `look` in the Troll Room (index 27) → outcome flips

Usage:
    python seed_path_demo.py --rom /path/to/zork1.z5 [--out [PATH]]

The ROM is not distributed here; see rom.py.

Deterministic by construction (fixed seed, fixed action lists) — no meta-seed
needed. `test_seed_path_artifact.py` re-derives the claims from the committed
artifact without needing the engine.

The printed summary is computed from the run, not asserted: this demo's premise —
every condition on one frozen tape — fails on a post-fix engine, and
`reading.describe_path_axis` says so rather than repeating a conclusion the
numbers no longer support. Unit-tested in `test_reading.py`.
"""
import argparse
import json
import os
from contextlib import closing

import jericho

import reading
import rom as rom_util

ROM = None  # resolved in main(); see rom.py for the resolution order
ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KILL_ACTION = "Kill troll with sword"
QUIET_INSERT_INDEX = 6   # above ground, before the house — no RNG-consuming NPC
RNG_INSERT_INDEX = 27    # inside the Troll Room, immediately before the kill
PAD_ACTION = "look"      # the SAME action string in both padded conditions


def walkthrough_prefix_through_troll():
    with closing(jericho.FrotzEnv(ROM)) as env:
        wt = env.get_walkthrough()
    kill_idx = next(i for i, a in enumerate(wt) if a.lower() == KILL_ACTION.lower())
    return wt[: kill_idx + 1]


def replay(actions):
    """Replay under the UNSEEDED default (the silent walkthrough tape).

    Closed on the way out, as in `seed_confound_demo.replay`.
    """
    with closing(jericho.FrotzEnv(ROM)) as env:
        env.reset()
        obs = None
        for a in actions:
            obs, _reward, done, _info = env.step(a)
            if done:
                break
        return {
            "resolved_seed": getattr(env, "_seed", None),
            "score": env.get_score(),
            "state_hash": env.get_world_state_hash(),
            "fight_obs": obs.strip(),
            "n_actions": len(actions),
        }


def main():
    global ROM
    ap = argparse.ArgumentParser()
    rom_util.add_rom_arguments(ap, "seed_path_demo.py")
    ap.add_argument("--out", nargs="?", const="", metavar="PATH",
                    help="Write the machine-readable artifact. Bare --out uses the "
                         "canonical data/seed_path_demo_jericho-<version>.json.")
    args = ap.parse_args()
    ROM = rom_util.resolve_from_args(args)

    base_actions = walkthrough_prefix_through_troll()
    conditions = []
    for name, acts in [
        ("baseline", base_actions),
        ("quiet padding x1",
         base_actions[:QUIET_INSERT_INDEX] + [PAD_ACTION] * 1 + base_actions[QUIET_INSERT_INDEX:]),
        ("quiet padding x3",
         base_actions[:QUIET_INSERT_INDEX] + [PAD_ACTION] * 3 + base_actions[QUIET_INSERT_INDEX:]),
        ("rng padding x1",
         base_actions[:RNG_INSERT_INDEX] + [PAD_ACTION] * 1 + base_actions[RNG_INSERT_INDEX:]),
    ]:
        r = replay(acts)
        r["condition"] = name
        conditions.append(r)

    base = conditions[0]
    for c in conditions:
        same = (c["state_hash"] == base["state_hash"]
                and c["score"] == base["score"]
                and c["fight_obs"] == base["fight_obs"])
        c["matches_baseline"] = same
        print(f"  {c['condition']:18} actions={c['n_actions']:2d} score={c['score']:3d} "
              f"matches_baseline={same}  fight: {c['fight_obs'][:60]!r}")

    print(f"\nReading (jericho {jericho.__version__}):")
    for line in reading.describe_path_axis(
            conditions, pad_action=PAD_ACTION,
            quiet_index=QUIET_INSERT_INDEX, rng_index=RNG_INSERT_INDEX):
        print(f"  - {line}")

    if args.out is not None:
        path = args.out or os.path.join(
            ARTIFACT_DIR, f"seed_path_demo_jericho-{jericho.__version__}.json")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        artifact = {
            "jericho_version": jericho.__version__,
            "rom": os.path.basename(ROM),
            "rom_sha256": rom_util.sha256(ROM),
            "kill_action": KILL_ACTION,
            "pad_action": PAD_ACTION,
            "quiet_insert_index": QUIET_INSERT_INDEX,
            "rng_insert_index": RNG_INSERT_INDEX,
            "base_action_list": base_actions,
            "conditions": conditions,
        }
        with open(path, "w") as fh:
            json.dump(artifact, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
