"""Locate and content-verify the Zork I game file.

Not distributed here (Zork I is proprietary), so a content hash is what ties a
reader's copy to the evidence: `EXPECTED_SHA256` is the `rom_sha256` every
artifact in `data/` records. `_NOT_FOUND` and `_MISMATCH` below carry the
reasoning where a reader meets it.

Resolution order: ``--rom PATH``, then ``$ZORK1_ROM``, then ``./zork1.z5``
beside this file.

Stdlib only, and it must stay that way: the artifact tests import this module and
run with no game engine installed.
"""
from __future__ import annotations

import hashlib
import os

#: SHA-256 of the Zork I release every committed artifact was generated against.
EXPECTED_SHA256 = "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd"

DEFAULT_BASENAME = "zork1.z5"
ENV_VAR = "ZORK1_ROM"

_HERE = os.path.dirname(os.path.abspath(__file__))

_NOT_FOUND = f"""Zork I game file not found.

This repository does not ship the ROM (Zork I is proprietary; Jericho does not
distribute game files either). Supply your own copy of {DEFAULT_BASENAME} — the
same file Jericho's supported-games list expects — and point the demo at it:

    python {{script}} --rom /path/to/{DEFAULT_BASENAME}
    ZORK1_ROM=/path/to/{DEFAULT_BASENAME} python {{script}}
    cp /path/to/{DEFAULT_BASENAME} {_HERE}/     # .gitignore keeps it uncommitted

Expected SHA-256: {EXPECTED_SHA256}

You do not need the ROM to check this repository's claims: the artifacts in
data/ are committed, and `pytest` re-derives every tabled number from them
without the engine. The ROM is only needed to regenerate those artifacts.
"""

_MISMATCH = """ROM content does not match the artifacts in data/.

    path:     {path}
    expected: {expected}
    actual:   {actual}

A different Zork I release will produce a different RNG tape, so re-running the
demos against this file would not reproduce the committed numbers — it would
generate new ones that silently disagree. Either supply the matching release, or
regenerate the artifacts from scratch and record the new hash (the demos write
`rom_sha256` into every artifact for exactly this reason).

To run anyway and accept the divergence, pass --no-verify-rom.
"""


def sha256(path: str) -> str:
    """Content hash of a file, read in chunks so a large ROM costs no memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_rom_arguments(parser, script_name: str = "seed_confound_demo.py") -> None:
    """Register the ROM flags shared by both demos."""
    parser.add_argument(
        "--rom", metavar="PATH",
        help=f"Path to {DEFAULT_BASENAME}. Falls back to ${ENV_VAR}, then to a "
             f"copy beside the script. Not distributed with this repository.")
    parser.add_argument(
        "--no-verify-rom", action="store_true",
        help="Skip the SHA-256 check. Only when regenerating artifacts "
             "against a different Zork I release.")
    parser.set_defaults(_script_name=script_name)


def resolve(cli_path: str | None = None, *, verify: bool = True,
            script_name: str = "seed_confound_demo.py") -> str:
    """Return a path to a usable Zork I ROM, or raise with instructions.

    `verify=False` permits a different release through; the demos then still
    record the actual hash in their artifact, so a divergence stays visible in
    the data rather than becoming an untracked difference in the environment.
    """
    candidates = [cli_path, os.environ.get(ENV_VAR),
                  os.path.join(_HERE, DEFAULT_BASENAME)]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            path = os.path.abspath(candidate)
            break
    else:
        raise SystemExit(_NOT_FOUND.format(script=script_name))

    if verify:
        actual = sha256(path)
        if actual != EXPECTED_SHA256:
            raise SystemExit(_MISMATCH.format(
                path=path, expected=EXPECTED_SHA256, actual=actual))
    return path


def resolve_from_args(args) -> str:
    """Convenience wrapper for a parser built with `add_rom_arguments`."""
    return resolve(args.rom, verify=not args.no_verify_rom,
                   script_name=getattr(args, "_script_name", "the demo"))
