"""awpack search finds shelf packs; install records a content hash that verify enforces."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from awpack import cli  # noqa: E402


def _shelf(tmp: Path) -> Path:
    shelf = tmp / "shelf"
    for pid, summary, tools in (("alpha", "reads PDFs", "[pdf_read]"),
                                ("beta", "drives a browser", "[pilot_open]")):
        d = shelf / pid
        d.mkdir(parents=True)
        (d / "pack.yaml").write_text(
            f"id: {pid}\nversion: 1.0.0\nsummary: {summary}\nstatus: preview\n"
            f"tools: {tools}\n", encoding="utf-8")
        (d / "README.md").write_text(f"# {pid}\n", encoding="utf-8")
    return shelf


def _json(argv, shelf):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv, shelf=shelf)
    return rc, json.loads(buf.getvalue())


def test_search_matches_id_summary_and_tools(tmp_path):
    shelf = _shelf(tmp_path)
    rc, obj = _json(["search", "pdf", "--json"], shelf)
    assert rc == 0 and [p["id"] for p in obj["packs"]] == ["alpha"]
    rc, obj = _json(["search", "pilot_open", "--json"], shelf)
    assert rc == 0 and [p["id"] for p in obj["packs"]] == ["beta"]
    rc, obj = _json(["search", "nothing-like-this", "--json"], shelf)
    assert rc == 0 and obj["packs"] == []


def test_search_on_an_unreadable_shelf_exits_2(tmp_path):
    rc, obj = _json(["search", "x", "--json"], tmp_path / "missing")
    assert rc == 2 and obj["ok"] is False


def test_install_records_sha256_and_verify_catches_tampering(tmp_path):
    shelf, dest = _shelf(tmp_path), tmp_path / "agents"
    rc, obj = _json(["install", "alpha", "--dest", str(dest), "--json"], shelf)
    assert rc == 0 and len(obj["sha256"]) == 64
    record = json.loads((dest / "alpha" / cli.INSTALL_RECORD).read_text(encoding="utf-8"))
    assert record["sha256"] == obj["sha256"] and record["source"].startswith("shelf:")
    rc, vobj = _json(["verify", "alpha", "--dest", str(dest), "--json"], shelf)
    assert rc == 0 and vobj["sha256"] == obj["sha256"]
    (dest / "alpha" / "README.md").write_text("# tampered\n", encoding="utf-8")
    rc, vobj = _json(["verify", "alpha", "--dest", str(dest), "--json"], shelf)
    assert rc == 1 and "changed since install" in vobj["detail"]


def test_search_is_a_listed_verb():
    assert "search" in cli.VERBS
