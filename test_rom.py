"""Guard the ROM contract.

This repository does not ship the game file, so the only thing tying a reader's
copy of Zork I to the committed artifacts is `rom.EXPECTED_SHA256`. If that
constant drifts from the `rom_sha256` recorded in `data/`, the demos accept a
release that cannot reproduce the tabled numbers. These tests keep the two in
lockstep.

Stdlib + pytest only; no engine, no ROM needed.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import rom

DATA = pathlib.Path(__file__).parent / "data"
ARTIFACTS = sorted(DATA.glob("*.json"))

#: Artifacts made by replaying the game, which therefore carry ROM provenance.
ROM_ARTIFACTS = sorted(DATA.glob("seed_*_demo_jericho-*.json"))
#: Artifacts that legitimately record no ROM: the prevalence screen reads source
#: code off GitHub and never boots the engine.
ROMLESS_PREFIXES = ("audit_frotzenv_seeding_",)


def test_artifacts_exist():
    assert ROM_ARTIFACTS, "no demo artifacts in data/ — the ROM contract has nothing to bind to"


@pytest.mark.parametrize("path", ROM_ARTIFACTS, ids=lambda p: p.stem)
def test_expected_hash_matches_every_artifact(path):
    """The hash the demos enforce must be the hash the evidence was made with."""
    recorded = json.loads(path.read_text())["rom_sha256"]
    assert recorded == rom.EXPECTED_SHA256, (
        f"{path.name} was generated against a different Zork I release than "
        "rom.EXPECTED_SHA256 accepts — one of the two is stale"
    )


@pytest.mark.parametrize("path", ROM_ARTIFACTS, ids=lambda p: p.stem)
def test_artifacts_name_the_expected_rom(path):
    assert json.loads(path.read_text())["rom"] == rom.DEFAULT_BASENAME


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.stem)
def test_no_artifact_escapes_the_rom_contract(path):
    """Every file in data/ is either engine-backed or explicitly not.

    Narrowing the two tests above to a glob would let a future engine-backed
    artifact that forgot to record `rom_sha256` pass by not matching. Each
    artifact must therefore land on one side of the line explicitly: demo
    artifacts declare a ROM, the prevalence screen declares none.
    """
    declares_rom = "rom_sha256" in json.loads(path.read_text())
    if path.name.startswith(ROMLESS_PREFIXES):
        assert not declares_rom, (
            f"{path.name} is named as a ROM-less artifact but records a ROM hash — "
            "if it now replays the game, drop it from ROMLESS_PREFIXES so the "
            "hash-lockstep tests cover it"
        )
    else:
        assert declares_rom, (
            f"{path.name} records no rom_sha256 and is not a known ROM-less "
            "artifact. If it is engine-backed, it must record the ROM it ran "
            "against; if not, add its prefix to ROMLESS_PREFIXES."
        )


def test_expected_hash_is_a_sha256():
    assert len(rom.EXPECTED_SHA256) == 64
    assert set(rom.EXPECTED_SHA256) <= set("0123456789abcdef")


def test_readme_quotes_the_enforced_hash():
    """The README prints the digest for readers; a transcription needs a check."""
    readme = (pathlib.Path(__file__).parent / "README.md").read_text()
    assert rom.EXPECTED_SHA256 in readme, (
        "README.md does not quote rom.EXPECTED_SHA256 — update it, or drop the "
        "digest from the prose so there is nothing to drift"
    )


def test_missing_rom_explains_itself(tmp_path, monkeypatch):
    """A reader without the ROM must get instructions, not a stack trace."""
    monkeypatch.delenv(rom.ENV_VAR, raising=False)
    monkeypatch.setattr(rom, "_HERE", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        rom.resolve(None, script_name="seed_confound_demo.py")
    message = str(exc.value)
    assert "not distributed" in message.lower() or "does not ship" in message.lower()
    assert rom.EXPECTED_SHA256 in message
    assert "--rom" in message


def test_mismatched_rom_is_refused(tmp_path, monkeypatch):
    """Wrong bytes are refused: accepting them would produce numbers that
    disagree with the paper with no indication why."""
    monkeypatch.delenv(rom.ENV_VAR, raising=False)
    decoy = tmp_path / rom.DEFAULT_BASENAME
    decoy.write_bytes(b"not a z-machine story file")
    with pytest.raises(SystemExit) as exc:
        rom.resolve(str(decoy))
    assert rom.EXPECTED_SHA256 in str(exc.value)
    assert rom.sha256(str(decoy)) in str(exc.value)


def test_verification_can_be_waived(tmp_path, monkeypatch):
    """--no-verify-rom exists for regenerating against another release; the
    resulting artifact still records the actual hash."""
    monkeypatch.delenv(rom.ENV_VAR, raising=False)
    decoy = tmp_path / rom.DEFAULT_BASENAME
    decoy.write_bytes(b"not a z-machine story file")
    assert rom.resolve(str(decoy), verify=False) == str(decoy.resolve())


def test_matching_rom_is_accepted(tmp_path, monkeypatch):
    """The happy path, which nothing else covers.

    A real Zork I ROM cannot be synthesized in a test, since that would mean
    finding a preimage of EXPECTED_SHA256, so the expected value is pinned to a
    decoy's digest instead. What is under test is that `resolve` accepts when the
    digests agree; every other verification test exercises a rejection path, which
    would still pass if `resolve` rejected everything."""
    monkeypatch.delenv(rom.ENV_VAR, raising=False)
    decoy = tmp_path / rom.DEFAULT_BASENAME
    decoy.write_bytes(b"stand-in for the real story file")
    monkeypatch.setattr(rom, "EXPECTED_SHA256", rom.sha256(str(decoy)))
    assert rom.resolve(str(decoy)) == str(decoy.resolve())


def test_cli_path_beats_environment(tmp_path, monkeypatch):
    chosen = tmp_path / "chosen.z5"
    chosen.write_bytes(b"x")
    other = tmp_path / "other.z5"
    other.write_bytes(b"y")
    monkeypatch.setenv(rom.ENV_VAR, str(other))
    assert rom.resolve(str(chosen), verify=False) == str(chosen.resolve())


def test_environment_used_when_no_flag(tmp_path, monkeypatch):
    target = tmp_path / "from_env.z5"
    target.write_bytes(b"x")
    monkeypatch.setenv(rom.ENV_VAR, str(target))
    assert rom.resolve(None, verify=False) == str(target.resolve())
