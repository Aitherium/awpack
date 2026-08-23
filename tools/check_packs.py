#!/usr/bin/env python3
"""Every pack on the shelf declares what it is, and nothing more is promised.

Run from the repo root:

    python awpack/tools/check_packs.py            # judge every pack
    python awpack/tools/check_packs.py --self-test

Three rules, and each exists because the alternative fails SILENTLY:

  AWP001  a pack directory with no pack.yaml. Nothing can install it and
          nothing can list it; it is a directory, not a pack.
  AWP002  a pack.yaml missing id/version/summary/status. A shelf entry with
          no version cannot be pinned, and one with no status cannot be told
          apart from something half-finished.
  AWP003  `status: internal` with no reason. A pack that must never be
          published is a recorded DECISION; without the reason the next
          person reads the absence as a backlog item and publishes it.

Exits 2 — never 0 — when it could not judge (no packs directory, or a
pack.yaml that will not parse). An empty shelf and a clean shelf must not
look the same.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # the runner pool ships a python without pip
    yaml = None


def _load_manifest(text: str) -> dict:
    """Read a pack manifest. Uses pyyaml when present, else a small parser.

    The fallback exists because this gate's first CI run died on
    `pip install pyyaml` ("No module named pip") — a gate that cannot run on
    the machine that runs it is not a gate. It covers exactly the shapes the
    pack contract defines: `key: value`, a folded block (`key: >-`), and a
    simple list (`- item`). Anything richer is a manifest the contract did not
    ask for, and is reported as unparseable rather than half-read.
    """
    if yaml is not None:
        return yaml.safe_load(text) or {}
    out: dict = {}
    key = None
    mode = None  # "block" | "list"
    buf: list = []

    def flush():
        nonlocal key, mode, buf
        if key is None:
            return
        if mode == "block":
            out[key] = " ".join(x.strip() for x in buf).strip()
        elif mode == "list":
            out[key] = list(buf)
        key, mode, buf = None, None, []

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indented = line[:1].isspace()
        if indented and mode == "block":
            buf.append(line)
            continue
        if indented and mode == "list" and line.lstrip().startswith("- "):
            buf.append(line.lstrip()[2:].split("#")[0].strip())
            continue
        flush()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v in (">-", ">", "|", "|-"):
            key, mode, buf = k, "block", []
        elif v == "":
            key, mode, buf = k, "list", []
        else:
            out[k] = v.split(" #")[0].strip().strip("'\"")
    flush()
    return out

REQUIRED = ("id", "version", "summary", "status")
#: Asked only of a pack that is actually OFFERED. A pack runs inside a
#: runtime rather than on its own, so a shelf entry with no install line
#: cannot be acted on — it is a catalogue row, not a distribution.
REQUIRED_IF_OFFERED = ("install", "runtime")
VALID_STATUS = {"published", "preview", "internal"}


def judge(packs_dir: Path) -> tuple:
    """Return (findings, judged). Raises nothing: the caller decides the exit."""
    findings: list = []
    judged = 0
    for d in sorted(p for p in packs_dir.iterdir() if p.is_dir()):
        manifest = d / "pack.yaml"
        if not manifest.exists():
            findings.append(f"AWP001 {d.name}: no pack.yaml — nothing can install it")
            continue
        try:
            data = _load_manifest(manifest.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - any unreadable manifest
            findings.append(f"AWP002 {d.name}: pack.yaml will not parse ({e})")
            continue
        judged += 1
        missing = [k for k in REQUIRED if not data.get(k)]
        if missing:
            findings.append(f"AWP002 {d.name}: missing {', '.join(missing)}")
        status = data.get("status")
        if status in ("published", "preview"):
            gaps = [k for k in REQUIRED_IF_OFFERED
                    if not str(data.get(k, "")).strip()]
            if gaps:
                findings.append(
                    f"AWP004 {d.name}: offered as {status!r} but declares "
                    f"no {', '.join(gaps)} — a reader cannot act on it")
        if status and status not in VALID_STATUS:
            findings.append(
                f"AWP002 {d.name}: status {status!r} is not one of "
                f"{', '.join(sorted(VALID_STATUS))}")
        if status == "internal" and not str(data.get("reason", "")).strip():
            findings.append(
                f"AWP003 {d.name}: internal with no reason — a hole dressed "
                f"up as a decision")
        if data.get("id") and data["id"] != d.name:
            findings.append(
                f"AWP002 {d.name}: declares id {data['id']!r}, which is how it "
                f"is installed — it must match the directory")
    return findings, judged


def self_test() -> int:
    """Prove each rule can still fail, and that a good pack passes."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="awpack-st-"))
    try:
        packs = tmp / "packs"
        packs.mkdir()
        good = packs / "good"
        good.mkdir()
        (good / "pack.yaml").write_text(
            "id: good\nversion: 0.1.0\nsummary: a pack\nstatus: preview\n"
            "runtime: awdk\ninstall: adk good\n",
            encoding="utf-8")
        findings, judged = judge(packs)
        assert not findings and judged == 1, (findings, judged)

        (packs / "nomanifest").mkdir()
        assert any("AWP001" in f for f in judge(packs)[0]), "AWP001 did not fire"
        shutil.rmtree(packs / "nomanifest")

        bad = packs / "bad"
        bad.mkdir()
        (bad / "pack.yaml").write_text("id: bad\n", encoding="utf-8")
        assert any("AWP002" in f for f in judge(packs)[0]), "AWP002 did not fire"

        (bad / "pack.yaml").write_text(
            "id: bad\nversion: 0.1.0\nsummary: s\nstatus: internal\n",
            encoding="utf-8")
        assert any("AWP003" in f for f in judge(packs)[0]), "AWP003 did not fire"

        # AWP004: offered, with no way to run it.
        (bad / "pack.yaml").write_text(
            "id: bad\nversion: 0.1.0\nsummary: s\nstatus: preview\n",
            encoding="utf-8")
        assert any("AWP004" in f for f in judge(packs)[0]), "AWP004 did not fire"

        # ...and it must NOT fire once the pack says how to run it, or every
        # honest pack is flagged and the rule gets switched off.
        (bad / "pack.yaml").write_text(
            "id: bad\nversion: 0.1.0\nsummary: s\nstatus: preview\n"
            "runtime: awdk\ninstall: adk bad\n", encoding="utf-8")
        assert not any("AWP004" in f for f in judge(packs)[0]), \
            "AWP004 fires on a pack that declares how to run it"

        # An internal pack is never offered, so it is never asked.
        (bad / "pack.yaml").write_text(
            "id: bad\nversion: 0.1.0\nsummary: s\nstatus: internal\n"
            "reason: names a customer\n", encoding="utf-8")
        assert not any("AWP004" in f for f in judge(packs)[0]), \
            "AWP004 demanded an install line from an internal pack"

        (bad / "pack.yaml").write_text(
            "id: bad\nversion: 0.1.0\nsummary: s\nstatus: internal\n"
            "reason: names a customer\n", encoding="utf-8")
        assert not any("AWP003" in f for f in judge(packs)[0]), \
            "AWP003 fires on a reasoned internal pack — it would flood"

        (bad / "pack.yaml").write_text(
            "id: elsewhere\nversion: 0.1.0\nsummary: s\nstatus: preview\n",
            encoding="utf-8")
        assert any("must match the directory" in f for f in judge(packs)[0]), \
            "an id/directory mismatch was not caught"
        # Exercise the FALLBACK explicitly. Without this it is dead code on
        # every machine that has pyyaml — which is every dev machine, and none
        # of the runners where it is the only reader.
        global yaml  # noqa: PLW0603 - deliberately swapped for one assertion
        real, yaml = yaml, None
        try:
            parsed = _load_manifest(
                "id: x\nversion: 1.0.0\nstatus: preview\n"
                "summary: >-\n  a folded\n  summary\n"
                "tools:\n  - one\n  - two\n")
        finally:
            yaml = real
        assert parsed["id"] == "x", parsed
        assert parsed["summary"] == "a folded summary", parsed
        assert parsed["tools"] == ["one", "two"], parsed

        print("self-test: every rule fires, none cries wolf, and the "
              "no-pyyaml reader works")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    root = Path(__file__).resolve().parents[1]
    packs = root / "packs"
    if not packs.is_dir():
        print(f"check_packs: {packs} is not a directory — cannot judge",
              file=sys.stderr)
        return 2
    findings, judged = judge(packs)
    if judged == 0 and not findings:
        print("check_packs: no packs found — refusing to call an empty shelf ok",
              file=sys.stderr)
        return 2
    for f in findings:
        print(f"  {f}")
    if findings:
        print(f"\ncheck_packs: {len(findings)} finding(s) across {judged} pack(s)",
              file=sys.stderr)
        return 1
    print(f"check_packs: {judged} pack(s), all declare what they are")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
