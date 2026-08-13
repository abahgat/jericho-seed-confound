#!/usr/bin/env python3
"""Clean fixed-vs-random engine-seed demonstration.

No model and no API calls, and that is the point: we replay a FIXED prefix of Jericho's
bundled Zork I walkthrough — the identical list of action strings on every run —
so the agent's behavior is constant *by construction*. The only thing that varies
between conditions is the engine seed. Any spread in the outcome is therefore pure
engine RNG, not policy.

Three seed regimes, all with the same fixed action sequence:
  1. default (unseeded)   -> Jericho binds the walkthrough seed (frozen tape)
  2. explicit seed=0       -> falsy-coalescing trap: `seed or bindings['seed']`
                              rebinds the walkthrough seed too (identical to #1)
  3. randomized positive   -> a fresh positive seed per run (the recommended fix)

Expected result on jericho <= 3.3.1: #1 and #2 collapse N "independent" runs to a
single realization (SD=0, one distinct world state) — an "average over N runs" is
N copies of one draw — while #3 varies across runs. The world-state-hash
DV is DV-agnostic: it captures ANY engine-RNG divergence (combat, thief, other
@random events), not only combat.

The printed summary is computed from the run, not asserted, so a post-fix engine
reports the confound as absent rather than claiming a collapse that did not
happen. See `reading.describe_seed_axis` for the reasoning, `test_reading.py` for
its tests.

Usage:
    python seed_confound_demo.py --rom /path/to/zork1.z5 [--actions K] [--runs N]

The ROM is not distributed here; see rom.py. You do not need it to check the
committed results — `pytest` re-derives every tabled number from data/ without
the engine.

Reproducible: the randomized condition draws its per-run seeds from a fixed
meta-seed, so the demonstration itself replays identically.
"""
import argparse
import json
import os
import random
import statistics as st
from contextlib import closing

import jericho

import reading
import rom as rom_util

ROM = None  # resolved in main(); see rom.py for the resolution order
META_SEED = 20260724  # fixes the DEMO's own seed draw so the demo is reproducible
# Canonical artifact directory. The committed files there ARE the paper's table —
# the note cites them so the number lives in a machine-readable record rather than
# only in prose. `test_seed_confound_artifact.py` validates them without jericho.
ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def replay(seed, actions):
    """Replay a fixed action list under one engine seed; return outcome DVs.

    Closed on the way out: each FrotzEnv loads its own private copy of
    libfrotz.so, so N un-closed runs hold N libraries and N Frotz VMs.
    """
    env = jericho.FrotzEnv(ROM, seed=seed) if seed is not None else jericho.FrotzEnv(ROM)
    with closing(env):
        env.reset()
        resolved = getattr(env, "_seed", None)  # Jericho stores the resolved engine seed
        done = False
        for a in actions:
            _obs, _reward, done, _info = env.step(a)
            if done:
                break
        try:
            state_hash = env.get_world_state_hash()
        except Exception:
            state_hash = None
        return {
            "resolved_seed": resolved,
            "score": env.get_score(),
            "state_hash": state_hash,
            "died": bool(done) and not env.victory(),
        }


def summarize(name, results):
    scores = [r["score"] for r in results]
    hashes = {r["state_hash"] for r in results}
    rseeds = sorted({r["resolved_seed"] for r in results if r["resolved_seed"] is not None})
    sd = st.pstdev(scores) if len(scores) > 1 else 0.0
    print(f"  {name:22} N={len(results):2d}  score mean={st.mean(scores):5.1f} SD={sd:5.2f} "
          f"(min={min(scores)}, max={max(scores)})  distinct_scores={len(set(scores))}  "
          f"distinct_world_states={len(hashes)}  deaths={sum(r['died'] for r in results)}")
    return {
        "condition": name,
        "n": len(results),
        "score_mean": st.mean(scores),
        "score_sd": sd,
        "score_min": min(scores),
        "score_max": max(scores),
        "distinct_scores": len(set(scores)),
        "distinct_world_states": len(hashes),
        "deaths": sum(r["died"] for r in results),
        "resolved_seeds": rseeds,
        "runs": results,
    }


def default_artifact_path():
    """One file per engine version: two versions' artifacts differing only in the
    `jericho_version` field ARE the note's version-invariance evidence."""
    return os.path.join(
        ARTIFACT_DIR, f"seed_confound_demo_jericho-{jericho.__version__}.json")


def main():
    global ROM
    ap = argparse.ArgumentParser()
    rom_util.add_rom_arguments(ap, "seed_confound_demo.py")
    ap.add_argument("--actions", type=int, default=40,
                    help="Fixed walkthrough-prefix length (default 40; past the troll fight).")
    ap.add_argument("--runs", type=int, default=12, help="Runs per condition (default 12).")
    ap.add_argument("--out", nargs="?", const="", metavar="PATH",
                    help="Write the machine-readable artifact. Bare --out uses the "
                         "canonical data/seed_confound_demo_jericho-<version>.json.")
    args = ap.parse_args()
    ROM = rom_util.resolve_from_args(args)

    with closing(jericho.FrotzEnv(ROM)) as wt_env:
        actions = wt_env.get_walkthrough()[:args.actions]
    print(f"Fixed policy: first {len(actions)} actions of Jericho's Zork I walkthrough "
          f"(identical every run).\n")

    d = summarize("default (unseeded)", [replay(None, actions) for _ in range(args.runs)])
    z = summarize("explicit seed=0", [replay(0, actions) for _ in range(args.runs)])
    rng = random.Random(META_SEED)
    seeds = [rng.randint(1, 2**31 - 1) for _ in range(args.runs)]
    r = summarize("randomized positive", [replay(s, actions) for s in seeds])

    print(f"\n  resolved engine seed  default={d['resolved_seeds'][:6]}  "
          f"seed0={z['resolved_seeds'][:6]}  random={r['resolved_seeds'][:6]}")
    print(f"\nReading (jericho {jericho.__version__}):")
    for line in reading.describe_seed_axis(d, z, r):
        print(f"  - {line}")

    if args.out is not None:
        path = args.out or default_artifact_path()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        artifact = {
            # Everything needed to re-derive the table, and to tell whether a
            # re-run that disagrees differs in the environment or in the finding.
            "jericho_version": jericho.__version__,
            "rom": os.path.basename(ROM),
            "rom_sha256": rom_util.sha256(ROM),
            "meta_seed": META_SEED,
            "actions": len(actions),
            "action_list": actions,
            "runs_per_condition": args.runs,
            "conditions": [d, z, r],
        }
        with open(path, "w") as fh:
            json.dump(artifact, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
