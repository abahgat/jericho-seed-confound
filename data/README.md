# Artifact schema

Two artifacts per engine version, written by the demos with `--out` and validated
by the tests in the parent directory. Every demonstration number the paper tables
comes from these files; nothing is transcribed by hand. The note's hand-verified
audit of the named systems is a code read and has no artifact here.

Their agreement across engine versions **is** the note's version-invariance
evidence: `seed_confound_demo_jericho-3.2.0.json` and
`…-3.3.1.json` must be identical in every field except `jericho_version`, and
`test_seed_confound_artifact.py::test_version_invariance` asserts exactly that.

## Shared provenance fields

| Field | Meaning |
|---|---|
| `jericho_version` | Engine version the run was made with |
| `rom` | Game file basename (always `zork1.z5`) |
| `rom_sha256` | Digest of the game file; must equal `rom.EXPECTED_SHA256` |

## `seed_confound_demo_jericho-*.json` — the seed axis

| Field | Meaning |
|---|---|
| `meta_seed` | Seed for the demo's *own* draw of the randomized condition's per-run seeds, so the demonstration itself replays identically |
| `actions` / `action_list` | Length of, and the full, fixed walkthrough prefix replayed every run |
| `runs_per_condition` | N per condition (12 as published) |
| `conditions[]` | Three entries: `default (unseeded)`, `explicit seed=0`, `randomized positive` |

Each condition carries `n`, `score_mean`, `score_sd`, `score_min`, `score_max`,
`distinct_scores`, `distinct_world_states`, `deaths`, `resolved_seeds` (the seeds
the engine actually bound, deduped and sorted) and `runs[]`.

Each run carries `resolved_seed`, `score`, `state_hash` (Jericho's world-state
hash — the DV, sensitive to *any* engine-RNG divergence, not only combat) and
`died`.

The headline reading: under `default` and `seed=0`, `resolved_seeds == [12]` and
`distinct_world_states == 1` — twelve "independent" runs are twelve copies of one
draw. Note that `action_list` is stored once at top level, shared by all three
conditions; behaviour-fixity is therefore a property of the schema rather than
something re-derivable from the file.

## `seed_path_demo_jericho-*.json` — the path axis

| Field | Meaning |
|---|---|
| `base_action_list` | Walkthrough prefix through `kill_action` |
| `kill_action` | The fight the conditions differ on (`Kill troll with sword`) |
| `pad_action` | The padding action, identical in both padded conditions (`look`) |
| `quiet_insert_index` | Where the RNG-quiet padding goes (6 — above ground, no hostile NPC) |
| `rng_insert_index` | Where the RNG-consuming padding goes (27 — inside the Troll Room) |
| `conditions[]` | Four entries: `baseline`, `quiet padding x1`, `quiet padding x3`, `rng padding x1` |

Each condition carries `resolved_seed` (always 12 — every condition runs on the
frozen tape), `score`, `state_hash`, `fight_obs` (the observation text at the
fight), `n_actions` and `matches_baseline`.

The headline reading: the two quiet-padding conditions match baseline in
`state_hash`, `score` and `fight_obs` despite a longer path, while `rng padding
x1` — the same `look`, one room deeper — differs in all three. Exposure tracks
RNG-consuming operations, not move count.

## `audit_frotzenv_seeding_<date>.json` — the prevalence screen

Written by `scripts/audit_frotzenv_seeding.py --json`. Unlike the demo artifacts,
this one is **not reproducible**: GitHub code search ranks rather than enumerates,
caps results, and returns a different set on each run. It is built to be
**re-verifiable** instead — every row pins the exact bytes its verdict came from.

| Field | Meaning |
|---|---|
| `generated_utc` | When the scan ran (UTC, second resolution) |
| `query` / `language` | The code-search query and language filter |
| `limit` / `raw_hits` / `limit_reached` | Requested cap, hits returned, and whether the cap was reached — `true` means a truncated sample |
| `gh_version` | The `gh` CLI that performed the search |
| `skip_repos` / `skip_path_pattern` | Exclusions applied before fetching: repositories skipped wholesale (the library itself, and this repository once it is searchable), and a path pattern for docs and tests. Recorded per run, so a change to either is visible in the artifact rather than only in the script |
| `files_considered` | Distinct (repo, path) pairs fetched, after dedupe, filtering and the non-public drop |
| `nonpublic_skipped` | How many files and repositories were dropped unfetched for not being public — code search is scoped to the running token, so an authenticated run reaches repos no reader could verify. Counts only: naming them would disclose private paths to no useful end |
| `fetch_failures[]` | Files the search returned but the contents API would not serve |
| `tally` | Both denominators, kept separate (below) |
| `results[]` | One row per classified call site |

Each row carries `repo`, `path`, `line`, `code` (the call-site line, stripped),
`verdict`, `is_fork`, `head_commit` (the repo's default-branch head at fetch
time), `permalink` (pinned to that commit and line) and `content_sha256` (digest
of the file text the verdict was computed from). A reader cannot repeat the
search, but can re-fetch any row's bytes and check the call.

`tally.by_call_site` and `tally.by_repo` are separate on purpose: one project with
fifteen `FrotzEnv(` lines contributes fifteen call sites, so "N% of call sites" is
not "N% of projects". `distinct_file_contents` below `files_considered` reveals
vendored or copied wrappers; `call_sites_in_forks` counts rows from forks.

Verdicts: `FROZEN` (no seed argument, or `seed=None`/`seed=0` — which re-bind the
walkthrough seed through the falsy-coalescing path), `SEEDED` (an explicit seed
keyword), `UNKNOWN` (positional arguments, a multi-line call, or a seed applied
elsewhere in the file — all routed to hand-checking rather than guessed at). The
classifier is unit-tested in `../test_audit_classifier.py`.

This run's counts are **not** restated here. The demo artifacts are
deterministic, so quoting their values is safe; this one is dated and
non-reproducible, and every prose copy is a separate thing to update. Read the
run instead: `tally.by_call_site` for the verdict split, `tally.by_repo` for the
repository denominator, `files_considered` and `nonpublic_skipped` for what was
and was not fetched.

`../test_audit_artifact.py` checks that the tally is arithmetic on `results[]`,
and that every row carries the commit, permalink and digest that make it
re-verifiable. The root README quotes one headline figure, checked against this
file. This is a screen, not a census — every call site that enters the paper is
hand-verified separately.

## License

CC BY 4.0; see [`LICENSE`](LICENSE) in this directory.
