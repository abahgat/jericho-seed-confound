"""Test the classifier behind the prevalence screen.

`scripts/audit_frotzenv_seeding.py` classifies each `FrotzEnv(...)` call site as
seeded or frozen, and that classification is what a field-level rate in the paper
would rest on. The search half needs the network and is not reproducible anyway
(GitHub code search ranks rather than enumerates); the classifier half is a pure
function of file text, so it can and should be pinned down here.

Stdlib + pytest; no network, no `gh`.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_PATH = pathlib.Path(__file__).parent / "scripts" / "audit_frotzenv_seeding.py"
_spec = importlib.util.spec_from_file_location("audit_frotzenv_seeding", _PATH)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def verdicts(source: str) -> list[str]:
    return [c["verdict"] for c in audit.classify_file(source)]


def test_no_call_sites_yields_nothing():
    assert verdicts("import jericho\nprint('hello')\n") == []


def test_bare_construction_is_frozen():
    """The ordinary construction, which passes no seed."""
    assert verdicts("env = FrotzEnv(rom_path)\n") == [audit.V_FROZEN_NONE]


def test_explicit_positive_seed_is_seeded():
    assert verdicts("env = FrotzEnv(rom, seed=42)\n") == [audit.V_SEEDED]


def test_minus_one_is_seeded():
    """-1 is Jericho's time-randomized seed: the recommended fix, not the bug."""
    assert verdicts("env = FrotzEnv(rom, seed=-1)\n") == [audit.V_SEEDED]


@pytest.mark.parametrize("literal", ["0", "None"])
def test_falsy_seed_is_frozen_not_seeded(literal):
    """`seed or bindings[...]` re-binds the walkthrough seed, so these look
    seeded and are not."""
    assert verdicts(f"env = FrotzEnv(rom, seed={literal})\n") == [audit.V_FROZEN_FALSY]


def test_positional_args_are_not_guessed():
    assert verdicts("env = FrotzEnv(rom, 42)\n") == [audit.V_UNKNOWN_POSITIONAL]


def test_nested_call_is_not_misread_as_frozen():
    """`FrotzEnv(os.path.join(a, b))` — the regex stops at the first paren, so
    the fragment holds a comma and routes to hand-checking rather than a verdict."""
    assert verdicts("env = FrotzEnv(os.path.join(d, 'zork1.z5'))\n") == [
        audit.V_UNKNOWN_POSITIONAL]


def test_multiline_call_is_flagged_not_dropped():
    src = "env = FrotzEnv(\n    rom,\n    seed=7,\n)\n"
    assert audit.V_UNKNOWN_MULTILINE in verdicts(src)


def test_post_hoc_seed_call_downgrades_frozen():
    """TextQuests' pattern: construct bare, seed afterwards. A constructor-only
    scan would score this FROZEN — a false positive against a repo that does
    seed. It must route to hand-checking instead."""
    src = "env = FrotzEnv(rom)\nif seed:\n    env.seed(seed)\n"
    assert verdicts(src) == [audit.V_UNKNOWN_POST_HOC]


def test_reset_with_seed_downgrades_frozen():
    """The wrapper pattern: the seed reaches the engine through reset()."""
    src = "env = FrotzEnv(rom)\nenv.reset(seed=game_seed)\n"
    assert verdicts(src) == [audit.V_UNKNOWN_POST_HOC]


def test_post_hoc_does_not_mask_an_explicit_falsy_seed():
    """A downgrade must not rescue a call site that is demonstrably trapped."""
    src = "env = FrotzEnv(rom, seed=0)\nenv.seed(x)\n"
    assert verdicts(src) == [audit.V_FROZEN_FALSY]


def test_line_numbers_are_reported():
    src = "import jericho\n\nenv = FrotzEnv(rom)\n"
    assert audit.classify_file(src)[0]["line"] == 3


def test_commented_out_call_is_not_a_call_site():
    """A commented-out construction is not a live call. Counting them inflated
    FROZEN and SEEDED alike; the screen scored two such lines in public repos."""
    assert verdicts("#env = FrotzEnv(rom)\n") == []
    assert verdicts("#   env = FrotzEnv(rom, seed=args.seed)\n") == []


def test_prose_about_the_constructor_is_not_a_call_site():
    """Comments and docstrings describing `FrotzEnv(...)` scored as frozen calls,
    which made this script classify its own documentation of the regex."""
    assert verdicts('"""Classify each FrotzEnv(...) call site in one file."""\n') == []
    assert verdicts("# `FrotzEnv(...)` up to the closing paren on the same line.\n") == []


def test_prose_is_not_read_as_a_multiline_call():
    """The multi-line heuristic keys on an unclosed paren, which prose trips."""
    assert verdicts("# for `FrotzEnv(` call sites, then a classification of\n") == []


def test_string_argument_survives_masking():
    """Masking blanks string contents in place, so a real call still classifies."""
    assert verdicts("env = FrotzEnv('zork1.z5', seed=1)\n") == [audit.V_SEEDED]
    assert verdicts('env = FrotzEnv("zork1.z5")\n') == [audit.V_FROZEN_NONE]


def test_trailing_comment_does_not_hide_a_real_call():
    assert verdicts("env = FrotzEnv(rom)  # no seed argument here\n") == [audit.V_FROZEN_NONE]


def test_commented_post_hoc_seed_does_not_downgrade():
    """A commented-out `env.seed(n)` must not rescue a live bare construction."""
    assert verdicts("env = FrotzEnv(rom)\n# env.seed(n)\n") == [audit.V_FROZEN_NONE]


def test_untokenizable_file_still_drops_comments():
    """Fallback path. An unterminated string makes `tokenize` raise, and this
    corpus holds such files; comments must still be masked."""
    src = '#env = FrotzEnv(rom, seed=1)\nenv = FrotzEnv(rom)\ntext = """unterminated\n'
    assert verdicts(src) == [audit.V_FROZEN_NONE]


def test_tally_separates_call_sites_from_repos():
    """One busy repo must not read as a field-wide majority."""
    rows = [
        {"repo": "a/one", "verdict": audit.V_FROZEN_NONE, "content_sha256": "x", "is_fork": False},
        {"repo": "a/one", "verdict": audit.V_FROZEN_NONE, "content_sha256": "x", "is_fork": False},
        {"repo": "a/one", "verdict": audit.V_FROZEN_NONE, "content_sha256": "x", "is_fork": False},
        {"repo": "b/two", "verdict": audit.V_SEEDED, "content_sha256": "y", "is_fork": True},
    ]
    t = audit.tally_rows(rows)
    assert t["by_call_site"] == {"FROZEN": 3, "SEEDED": 1}
    assert t["by_repo"] == {"repos_total": 2, "repos_with_any_frozen": 1, "repos_all_seeded": 1}
    assert t["distinct_file_contents"] == 2
    assert t["call_sites_in_forks"] == 1
