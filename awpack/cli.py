#!/usr/bin/env python3
"""awpack: install and manage agent packs from the shelf.

CONTRACT:
  awpack list [--json]                        list packs on the shelf
  awpack show <id>                            render manifest for a human
  awpack install <id> [--dest DIR] [--replace] [--json]
                                              resolve deps, check runtime, install
  awpack verify <id> [--dest DIR] [--json]    is the pack installed and loadable?
  awpack remove <id> [--dest DIR] [--json]    uninstall a pack from the install dir
  awpack --self-test                          prove every rule can still fail
  awpack --list-verbs                         one verb per line

Install dir: --dest DIR, else $AWPACK_INSTALL_DIR, else ~/.aither/agents. An awnix
appliance installs packs to /var/lib/awnix/packs through `awnix component` (the
`pack` backend), which passes --dest. `install --ref <commit>` is accepted and
ignored: the pin is the shelf the caller put on AWPACK_SHELF (a baked copy at the
locked commit), not something awpack fetches. `install --replace` swaps an
installed copy for the shelf's in one rename (the old copy is restored if the swap
fails) -- that is how `awnix component sync` moves a pack to a new lock pin after
`bootc upgrade` / `bootc rollback` changes the baked shelf.

--json prints ONE object on stdout: {ok, op, id?, dest?, packs?, detail}; human
messages go to stderr so a caller can parse stdout unconditionally.

Exit codes:
  0: success (list, show succeeded; install/verify completed; self-test passed)
  1: refused (pack not found, runtime unmet, deps unmet, already installed, etc.)
  2: cannot judge (shelf unreadable, manifest unparseable, etc.)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

VERBS = ("list", "show", "install", "verify", "remove")

#: Who stands behind a shelf, declared in its `shelf.yaml`. A shelf with no
#: shelf.yaml is `unlabelled` and behaves exactly as before (awnix points
#: AWPACK_SHELF at an unlabelled copy of this shelf; that must keep working).
#: `community` is everyone else's packs: listed and shown like any other, but
#: never installed without an explicit --allow-community, because nobody here
#: built or reviewed them.
PROVENANCES = ("first-party", "community")

try:
    import yaml
except ImportError:
    yaml = None


def _load_manifest(text: str) -> dict:
    """Read a pack manifest. Uses pyyaml when present, else a small parser.

    Covers: `key: value`, folded blocks (`key: >-`), simple lists (`- item`).
    """
    if yaml is not None:
        return yaml.safe_load(text) or {}
    out: dict = {}
    key = None
    mode = None
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


class PackRegistry:
    """Read and query the pack shelf."""

    def __init__(self, shelf_dir: Path):
        self.shelf = shelf_dir
        self.packs: dict = {}
        self.errors: list = []
        self.provenance = "unlabelled"

    def discover(self) -> int:
        """Scan shelf for packs. Return count discovered, or 0 if shelf unreadable."""
        if not self.shelf.is_dir():
            self.errors.append(f"shelf {self.shelf} is not a directory")
            return 0
        label = self.shelf / "shelf.yaml"
        if label.is_file():
            try:
                declared = str(_load_manifest(label.read_text(encoding="utf-8"))
                               .get("provenance") or "").strip()
            except Exception as e:
                self.errors.append(f"shelf.yaml unreadable: {e}")
                return 0
            if declared not in PROVENANCES:
                # A label we cannot read is not "unlabelled": someone tried to say
                # who stands behind this shelf, and guessing which would be worse.
                self.errors.append(
                    f"shelf.yaml provenance {declared!r} is not one of "
                    f"{', '.join(PROVENANCES)}")
                return 0
            self.provenance = declared
        try:
            pack_dirs = sorted(p for p in self.shelf.iterdir() if p.is_dir())
        except (OSError, PermissionError) as e:
            self.errors.append(f"cannot read shelf: {e}")
            return 0
        for d in pack_dirs:
            manifest_file = d / "pack.yaml"
            if not manifest_file.exists():
                self.errors.append(f"{d.name}: no pack.yaml")
                continue
            try:
                data = _load_manifest(manifest_file.read_text(encoding="utf-8"))
            except Exception as e:
                self.errors.append(f"{d.name}: pack.yaml unreadable: {e}")
                continue
            if not data.get("id"):
                self.errors.append(f"{d.name}: no id field")
                continue
            if data["id"] != d.name:
                self.errors.append(
                    f"{d.name}: declares id {data['id']!r}, must match directory"
                )
                continue
            data["_dir"] = d
            self.packs[d.name] = data
        return len(self.packs)

    def get(self, pack_id: str) -> dict | None:
        """Fetch one pack manifest, or None if not found."""
        return self.packs.get(pack_id)

    def all(self) -> dict:
        """Return all discovered packs as {id: manifest}."""
        return self.packs


def install_root(dest: str | Path | None = None, env: dict | None = None) -> Path:
    """Where packs are installed: --dest, else AWPACK_INSTALL_DIR, else ~/.aither/agents."""
    if dest:
        return Path(dest).expanduser()
    env = os.environ if env is None else env
    explicit = (env.get("AWPACK_INSTALL_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".aither" / "agents"


def _emit(as_json: bool, payload: dict) -> None:
    """Print the one JSON object a --json caller parses (stdout only)."""
    if as_json:
        print(json.dumps(payload, sort_keys=True, default=str))


def cmd_list(registry: PackRegistry, as_json: bool = False) -> int:
    """List all packs on the shelf."""
    if registry.errors:
        for err in registry.errors:
            print(f"  {err}", file=sys.stderr)
        _emit(as_json, {"ok": False, "op": "list", "packs": [],
                        "detail": "; ".join(registry.errors)})
        return 2
    if not registry.packs:
        print("no packs on the shelf", file=sys.stderr)
        _emit(as_json, {"ok": False, "op": "list", "packs": [],
                        "detail": f"no packs on the shelf {registry.shelf}"})
        return 2
    if as_json:
        _emit(True, {"ok": True, "op": "list", "detail": "",
                     "provenance": registry.provenance, "packs": [
            {"id": pid, "version": str(m.get("version", "")),
             "status": str(m.get("status", "")),
             "summary": str(m.get("summary", "")),
             "provenance": registry.provenance}
            for pid, m in sorted(registry.packs.items())]})
        return 0
    print(f"Packs on shelf ({registry.provenance}):\n")
    for pack_id, manifest in sorted(registry.packs.items()):
        version = manifest.get("version", "?")
        status = manifest.get("status", "?")
        summary = manifest.get("summary", "")[:60]
        print(f"  {pack_id:<20} {version:<10} {status:<12} {summary}")
    return 0


def cmd_show(registry: PackRegistry, pack_id: str) -> int:
    """Show one pack's manifest."""
    if registry.errors:
        for err in registry.errors:
            print(f"  {err}", file=sys.stderr)
        return 2
    if not registry.packs:
        # An EMPTY shelf cannot answer "does this pack exist". Reporting
        # "not found" (1) would be a verdict we have no basis for -- it reads
        # as "that pack is not a thing" when the truth is "I can see nothing
        # at all". cmd_list already calls this 2; these two must agree, or the
        # exit code means something different depending on which you called.
        print("no packs on the shelf -- cannot say whether "
              f"{pack_id!r} exists", file=sys.stderr)
        return 2
    manifest = registry.get(pack_id)
    if not manifest:
        print(f"pack not found: {pack_id!r}", file=sys.stderr)
        return 1
    d = manifest["_dir"]
    manifest_file = d / "pack.yaml"
    print(f"Pack: {pack_id}  [{registry.provenance}]\n")
    print(manifest_file.read_text(encoding="utf-8"))
    return 0


def _parse_version_req(req: str) -> tuple[str, str]:
    """Parse a version requirement like 'awdk>=3.7.4' -> ('awdk', '>=3.7.4').

    Returns (package_name, operator_and_version) or ('', '') if unparseable.
    """
    req = req.strip()
    for op in (">=", "<=", "==", "!=", ">", "<", "~="):
        if op in req:
            pkg, _, ver = req.partition(op)
            return pkg.strip(), op + ver.strip()
    return req, ""


# The runtime check reads DISTRIBUTION metadata, never __import__: a pip name is
# not an import name (awdk imports as `adk`), so `__import__("awdk")` refused
# every pack on a machine with awdk 3.8.24 installed (w1b-19-04).


def _version_tuple(v: str) -> tuple:
    """'3.8.24' -> (3, 8, 24); stops at the first non-numeric segment."""
    out = []
    for part in v.strip().split("."):
        num = ""
        for ch in part:
            if not ch.isdigit():
                break
            num += ch
        if not num:
            break
        out.append(int(num))
        if len(num) != len(part):
            break
    return tuple(out)


def _version_satisfies(installed: str, spec: str) -> bool | None:
    """Does `installed` satisfy `spec` (e.g. '>=3.7.4')? None = cannot judge."""
    try:
        from packaging.specifiers import InvalidSpecifier, SpecifierSet
        from packaging.version import InvalidVersion, Version
        try:
            return Version(installed) in SpecifierSet(spec)
        except (InvalidSpecifier, InvalidVersion):
            return None
    except ImportError:
        pass
    for op in (">=", "<=", "==", "!=", "~=", ">", "<"):
        if spec.startswith(op):
            want = _version_tuple(spec[len(op):])
            have = _version_tuple(installed)
            if not want or not have:
                return None
            n = max(len(want), len(have))
            have_p = have + (0,) * (n - len(have))
            want_p = want + (0,) * (n - len(want))
            if op == "~=":
                prefix = want[:-1] if len(want) > 1 else want
                return have_p >= want_p and have[:len(prefix)] == prefix
            return {
                ">=": have_p >= want_p, "<=": have_p <= want_p,
                "==": have_p == want_p, "!=": have_p != want_p,
                ">": have_p > want_p, "<": have_p < want_p,
            }[op]
    return None


def _installed_version(dist_name: str) -> str | None:
    """Installed version of a DISTRIBUTION (pip name), or None if absent."""
    from importlib import metadata
    for name in (dist_name, dist_name.replace("-", "_"), dist_name.replace("_", "-")):
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return None


def _check_runtime(runtime_req: str) -> tuple[bool, str]:
    """Check if a runtime requirement like 'awdk>=3.7.4' is met.

    Returns (satisfied, message). Resolves the DISTRIBUTION via
    importlib.metadata (a pip name is not an import name) and checks the version
    specifier. A version that cannot be parsed is refused -- an unverified
    runtime is not a satisfied one.
    """
    if not runtime_req.strip():
        return True, "no runtime requirement"
    pkg_name, version_spec = _parse_version_req(runtime_req)
    if not version_spec:
        pkg_name = runtime_req.strip()
    if not pkg_name:
        return True, "unparseable requirement (ignored)"
    installed = _installed_version(pkg_name)
    if installed is None:
        return False, f"{pkg_name} not found (required: {runtime_req})"
    if not version_spec:
        return True, f"{pkg_name} {installed} is installed"
    ok = _version_satisfies(installed, version_spec)
    if ok is None:
        return False, (f"{pkg_name} {installed} is installed but {version_spec!r} "
                       f"could not be judged (required: {runtime_req})")
    if not ok:
        return False, f"{pkg_name} {installed} does not satisfy {runtime_req}"
    return True, f"{pkg_name} {installed} satisfies {runtime_req}"


def _refuse(as_json: bool, op: str, pack_id: str, dest: Path | None,
            msg: str, rc: int) -> int:
    """Report a refusal on stderr (and as JSON when asked) and return rc."""
    print(msg, file=sys.stderr)
    _emit(as_json, {"ok": False, "op": op, "id": pack_id,
                    "dest": str(dest) if dest else "", "detail": msg})
    return rc


def cmd_install(registry: PackRegistry, pack_id: str,
                dest: str | Path | None = None, as_json: bool = False,
                replace: bool = False, allow_community: bool = False) -> int:
    """Install a pack to <install_root>/<id>.

    Steps:
    1. Find pack manifest
    2. Check runtime requirement
    3. Check dependencies (needs)
    4. Create install dir if needed
    5. Copy pack files (to a temp sibling, then rename -- never a half copy)
    6. Print the install command from manifest
    """
    agents_dir = install_root(dest)
    if registry.errors:
        return _refuse(as_json, "install", pack_id, agents_dir,
                       "; ".join(registry.errors), 2)
    manifest = registry.get(pack_id)
    if not manifest:
        return _refuse(as_json, "install", pack_id, agents_dir,
                       f"pack not found: {pack_id!r}", 1)
    if registry.provenance == "community" and not allow_community:
        return _refuse(as_json, "install", pack_id, agents_dir,
                       f"{pack_id!r} is a COMMUNITY pack: nobody at Aitherium built or "
                       f"reviewed it. Read {manifest['_dir']} first, then re-run with "
                       f"--allow-community to install it.", 1)

    # Check runtime requirement
    runtime_req = manifest.get("runtime", "").strip()
    if runtime_req:
        satisfied, msg = _check_runtime(runtime_req)
        if not satisfied:
            return _refuse(as_json, "install", pack_id, agents_dir,
                           f"runtime not satisfied: {msg}", 1)

    # Check dependencies
    needs = manifest.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    unmet = [n for n in needs if n not in registry.packs]
    if unmet:
        return _refuse(as_json, "install", pack_id, agents_dir,
                       f"unmet dependencies: {', '.join(unmet)}", 1)

    install_dir = agents_dir / pack_id
    if install_dir.exists() and not replace:
        return _refuse(as_json, "install", pack_id, agents_dir,
                       f"already installed at {install_dir}; "
                       f"`awpack remove {pack_id}` first, or pass --replace", 1)
    if install_dir.exists() and not (install_dir / "pack.yaml").is_file():
        # --replace swaps a PACK, never someone's unrelated folder
        return _refuse(as_json, "install", pack_id, agents_dir,
                       f"{install_dir} exists but is not a pack; refusing to replace", 1)

    tmp_dir = agents_dir / f".{pack_id}.installing"
    old_dir = agents_dir / f".{pack_id}.replaced"
    moved_old = False
    try:
        agents_dir.mkdir(parents=True, exist_ok=True)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        shutil.copytree(manifest["_dir"], tmp_dir)
        if install_dir.exists():
            if old_dir.exists():
                shutil.rmtree(old_dir)
            os.replace(install_dir, old_dir)
            moved_old = True
        os.replace(tmp_dir, install_dir)
    except (OSError, PermissionError) as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if moved_old and not install_dir.exists():
            try:
                os.replace(old_dir, install_dir)
            except OSError as e2:
                # The restore failed too: the previous version still sits at old_dir.
                # Say where, so an operator can move it back by hand.
                print(f"awpack: could not restore the previous {pack_id} from {old_dir}: {e2}",
                      file=sys.stderr)
        return _refuse(as_json, "install", pack_id, agents_dir,
                       f"install failed: {e}", 1)
    if moved_old:
        shutil.rmtree(old_dir, ignore_errors=True)

    install_cmd = manifest.get("install", "").strip()
    if as_json:
        _emit(True, {"ok": True, "op": "install", "id": pack_id,
                     "provenance": registry.provenance,
                     "dest": str(install_dir),
                     "version": str(manifest.get("version", "")),
                     "next": install_cmd, "detail": ""})
        return 0
    # Print the install command from manifest (user must run it)
    print(f"installed {pack_id} to {install_dir}\n")
    if install_cmd:
        print("Next, run:")
        print()
        for line in install_cmd.splitlines():
            print(f"  {line}")
        print()
    return 0


def cmd_remove(registry: PackRegistry, pack_id: str,
               dest: str | Path | None = None, as_json: bool = False) -> int:
    """Remove an installed pack from <install_root>/<id>.

    Judged against the INSTALL dir, not the shelf: a pack dropped from a newer
    shelf must still be removable. Refuses (1) when it is not installed, and
    refuses a directory that is not a pack (no pack.yaml, or a different id) so a
    wrong --dest never deletes someone's unrelated folder.
    """
    agents_dir = install_root(dest)
    if not pack_id or "/" in pack_id or "\\" in pack_id or pack_id in (".", ".."):
        return _refuse(as_json, "remove", pack_id, agents_dir,
                       f"invalid pack id: {pack_id!r}", 1)
    install_dir = agents_dir / pack_id
    manifest_file = install_dir / "pack.yaml"
    if not install_dir.exists():
        return _refuse(as_json, "remove", pack_id, agents_dir,
                       f"pack {pack_id!r} not installed (no {install_dir})", 1)
    try:
        installed = _load_manifest(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return _refuse(as_json, "remove", pack_id, agents_dir,
                       f"{install_dir} is not an installed pack ({e}); refusing", 1)
    if installed.get("id") != pack_id:
        return _refuse(as_json, "remove", pack_id, agents_dir,
                       f"{install_dir} declares id {installed.get('id')!r}; refusing", 1)
    trash = agents_dir / f".{pack_id}.removing"
    try:
        if trash.exists():
            shutil.rmtree(trash)
        os.replace(install_dir, trash)
        shutil.rmtree(trash)
    except (OSError, PermissionError) as e:
        return _refuse(as_json, "remove", pack_id, agents_dir,
                       f"remove failed: {e}", 1)
    if as_json:
        _emit(True, {"ok": True, "op": "remove", "id": pack_id,
                     "dest": str(install_dir), "detail": ""})
    else:
        print(f"removed {pack_id} from {install_dir}")
    return 0


def cmd_verify(registry: PackRegistry, pack_id: str,
               dest: str | Path | None = None, as_json: bool = False) -> int:
    """Verify pack is installed and loadable.

    Returns 0 if pack.yaml exists at expected location, 1 if not.
    """
    agents_dir = install_root(dest)
    if registry.errors:
        return _refuse(as_json, "verify", pack_id, agents_dir,
                       "; ".join(registry.errors), 2)
    manifest = registry.get(pack_id)
    if not manifest:
        return _refuse(as_json, "verify", pack_id, agents_dir,
                       f"pack not found in shelf: {pack_id!r}", 1)

    install_dir = agents_dir / pack_id
    manifest_file = install_dir / "pack.yaml"
    if not manifest_file.exists():
        return _refuse(as_json, "verify", pack_id, agents_dir,
                       f"pack {pack_id!r} not installed (expected at {manifest_file})", 1)

    try:
        installed = _load_manifest(manifest_file.read_text(encoding="utf-8"))
    except Exception as e:
        return _refuse(as_json, "verify", pack_id, agents_dir,
                       f"installed pack.yaml corrupted: {e}", 1)

    if installed.get("id") != pack_id:
        return _refuse(as_json, "verify", pack_id, agents_dir,
                       f"installed pack id mismatch: expected {pack_id!r}, "
                       f"got {installed.get('id')!r}", 1)

    if as_json:
        _emit(True, {"ok": True, "op": "verify", "id": pack_id,
                     "dest": str(install_dir),
                     "version": str(installed.get("version", "")), "detail": ""})
        return 0
    print(f"pack {pack_id!r} is installed and loadable")
    print(f"  location: {install_dir}")
    print(f"  version:  {installed.get('version', '?')}")
    return 0


def _self_test() -> int:
    """Prove each command works and can refuse properly."""
    tmp = Path(tempfile.mkdtemp(prefix="awpack-cli-st-"))
    try:
        # Set up a test shelf
        shelf = tmp / "shelf"
        shelf.mkdir()

        # Create a good pack
        good_dir = shelf / "test_pack"
        good_dir.mkdir()
        (good_dir / "pack.yaml").write_text(
            "id: test_pack\n"
            "version: 1.0.0\n"
            "summary: a test pack\n"
            "status: preview\n"
            "install: echo 'test pack installed'\n"
            "needs: []\n",
            encoding="utf-8",
        )
        (good_dir / "README.md").write_text("# Test Pack\n", encoding="utf-8")

        # Create a pack with unmet dependency
        dep_dir = shelf / "needs_missing"
        dep_dir.mkdir()
        (dep_dir / "pack.yaml").write_text(
            "id: needs_missing\n"
            "version: 1.0.0\n"
            "summary: pack with missing dep\n"
            "status: preview\n"
            "runtime: sys\n"
            "install: echo 'never'\n"
            "needs: [nonexistent]\n",
            encoding="utf-8",
        )

        # Create a pack with missing runtime
        bad_rt = shelf / "bad_runtime"
        bad_rt.mkdir()
        (bad_rt / "pack.yaml").write_text(
            "id: bad_runtime\n"
            "version: 1.0.0\n"
            "summary: bad runtime req\n"
            "status: preview\n"
            "runtime: nonexistent_package_xyz_12345>=99.0.0\n"
            "install: echo 'nope'\n"
            "needs: []\n",
            encoding="utf-8",
        )

        # Test list
        registry = PackRegistry(shelf)
        assert registry.discover() == 3
        assert cmd_list(registry) == 0

        # Test show (existing pack)
        assert cmd_show(registry, "test_pack") == 0
        # Test show (nonexistent pack)
        assert cmd_show(registry, "nonexistent") == 1

        # Test install — must refuse unmet dep
        assert cmd_install(registry, "needs_missing") == 1
        # Test install — must refuse bad runtime
        assert cmd_install(registry, "bad_runtime") == 1
        # Test install -- into a TEMP dest, never the caller's home
        agents = tmp / "agents"
        assert cmd_install(registry, "test_pack", dest=agents) == 0
        assert cmd_verify(registry, "test_pack", dest=agents) == 0
        assert (agents / "test_pack" / "pack.yaml").is_file()
        # a second install refuses rather than overwriting
        assert cmd_install(registry, "test_pack", dest=agents) == 1
        # --replace swaps the installed copy for the shelf's (a new lock pin)
        (agents / "test_pack" / "stale.txt").write_text("old", encoding="utf-8")
        assert cmd_install(registry, "test_pack", dest=agents, replace=True) == 0
        assert (agents / "test_pack" / "pack.yaml").is_file()
        assert not (agents / "test_pack" / "stale.txt").exists(), "replace kept the old copy"
        assert not (agents / ".test_pack.replaced").exists()
        # --replace never deletes a directory that is not a pack
        bogus = agents / "bad_runtime"
        bogus.mkdir(parents=True)
        (bogus / "keep.txt").write_text("x", encoding="utf-8")
        reg_b = PackRegistry(shelf)
        reg_b.discover()
        reg_b.packs["bad_runtime"] = {**reg_b.packs["bad_runtime"], "runtime": ""}
        assert cmd_install(reg_b, "bad_runtime", dest=agents, replace=True) == 1
        assert (bogus / "keep.txt").is_file(), "replace deleted a non-pack dir"
        shutil.rmtree(bogus)

        # DEST OVERRIDE: AWPACK_INSTALL_DIR steers the default, --dest beats it
        env_dir = tmp / "env-agents"
        assert install_root(None, {"AWPACK_INSTALL_DIR": str(env_dir)}) == env_dir
        assert install_root(agents, {"AWPACK_INSTALL_DIR": str(env_dir)}) == agents
        assert install_root(None, {}) == Path.home() / ".aither" / "agents"

        # REMOVE ROUND-TRIP: remove, verify refuses, remove again refuses
        assert cmd_remove(registry, "test_pack", dest=agents) == 0
        assert not (agents / "test_pack").exists()
        assert cmd_verify(registry, "test_pack", dest=agents) == 1
        assert cmd_remove(registry, "test_pack", dest=agents) == 1
        # remove refuses a directory that is not that pack, and path tricks
        stray = agents / "not_a_pack"
        stray.mkdir(parents=True)
        (stray / "keep.txt").write_text("x", encoding="utf-8")
        assert cmd_remove(registry, "not_a_pack", dest=agents) == 1
        assert (stray / "keep.txt").is_file(), "remove deleted a non-pack dir"
        assert cmd_remove(registry, "../agents", dest=agents) == 1

        # JSON SHAPE: one object on stdout with ok/op/id/dest/detail
        import contextlib
        import io

        def run_json(fn, *a, **kw):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fn(*a, **kw)
            return rc, json.loads(buf.getvalue())

        rc, obj = run_json(cmd_install, registry, "test_pack", dest=agents, as_json=True)
        assert rc == 0 and obj["ok"] is True and obj["op"] == "install"
        assert obj["id"] == "test_pack" and obj["dest"].endswith("test_pack")
        assert obj["version"] == "1.0.0"
        rc, obj = run_json(cmd_verify, registry, "test_pack", dest=agents, as_json=True)
        assert rc == 0 and obj["op"] == "verify" and obj["ok"] is True
        rc, obj = run_json(cmd_remove, registry, "test_pack", dest=agents, as_json=True)
        assert rc == 0 and obj == {"ok": True, "op": "remove", "id": "test_pack",
                                   "dest": obj["dest"], "detail": ""}
        rc, obj = run_json(cmd_remove, registry, "test_pack", dest=agents, as_json=True)
        assert rc == 1 and obj["ok"] is False and obj["detail"]
        rc, obj = run_json(cmd_list, registry, as_json=True)
        assert rc == 0 and obj["op"] == "list"
        assert {p["id"] for p in obj["packs"]} == {"test_pack", "needs_missing", "bad_runtime"}
        rc, obj = run_json(cmd_install, registry, "bad_runtime", dest=agents, as_json=True)
        assert rc == 1 and obj["ok"] is False and "runtime" in obj["detail"]

        # argv plumbing: main() honours --dest and --json
        rc, obj = run_json(main, ["install", "test_pack", "--dest", str(agents),
                                  "--json", "--ref", "0" * 40], shelf=shelf)
        assert rc == 0 and obj["ok"] and (agents / "test_pack").is_dir()
        rc, obj = run_json(main, ["install", "test_pack", "--dest", str(agents),
                                  "--json", "--replace"], shelf=shelf)
        assert rc == 0 and obj["ok"], "main() must honour --replace"
        rc, obj = run_json(main, ["remove", "test_pack", "--dest", str(agents),
                                  "--json"], shelf=shelf)
        assert rc == 0 and not (agents / "test_pack").exists()

        # Test empty shelf
        empty_shelf = tmp / "empty"
        empty_shelf.mkdir()
        reg3 = PackRegistry(empty_shelf)
        assert reg3.discover() == 0
        assert cmd_list(reg3) == 2  # should refuse empty shelf

        # EXIT 2 IS A CONTRACT, AND THIS ARM EXISTS BECAUSE IT WAS VACUOUS.
        # Mutating `return 2` -> `return 0` in cmd_list left the self-test
        # PASSING, so the cannot-judge path was asserted by nothing. A probe
        # that cannot judge must never report success -- an empty shelf and a
        # healthy one must not look the same.
        empty = Path(tmp) / "empty-shelf"
        empty.mkdir(exist_ok=True)
        reg_empty = PackRegistry(empty)
        reg_empty.discover()
        rc = cmd_list(reg_empty)
        assert rc == 2, f"empty shelf must exit 2 (cannot judge), got {rc}"
        reg_empty2 = PackRegistry(empty)
        reg_empty2.discover()
        rc = cmd_show(reg_empty2, "anything")
        assert rc == 2, f"show on an empty shelf must exit 2, got {rc}"

        # ...and a shelf that DOES have packs must not be reported as
        # unjudgeable. Uses the REAL shelf: the temp one above has had bad
        # manifests written into it by earlier arms, so reusing it would make
        # this assertion depend on arm order rather than on the rule.
        real_shelf = Path(__file__).resolve().parent.parent / "packs"
        if real_shelf.is_dir():
            reg_real = PackRegistry(real_shelf)
            reg_real.discover()
            rc = cmd_list(reg_real)
            assert rc == 0, f"a populated shelf must exit 0, got {rc}"

        # Provenance. A community shelf lists normally, refuses install without
        # --allow-community, installs with it; a garbled label is an error, not
        # "unlabelled"; the shipped shelf says first-party.
        comm = tmp / "community"
        (comm / "cpack").mkdir(parents=True)
        (comm / "shelf.yaml").write_text("provenance: community\n", encoding="utf-8")
        (comm / "cpack" / "pack.yaml").write_text(
            "id: cpack\nversion: 0.1.0\nsummary: someone else's\nstatus: preview\n",
            encoding="utf-8")
        reg_c = PackRegistry(comm)
        reg_c.discover()
        assert reg_c.provenance == "community", reg_c.provenance
        assert cmd_list(reg_c) == 0, "a community shelf must still list"
        cdest = tmp / "cdest"
        rc = cmd_install(reg_c, "cpack", dest=cdest)
        assert rc == 1 and not (cdest / "cpack").exists(), \
            "a community pack installed WITHOUT --allow-community"
        rc = cmd_install(reg_c, "cpack", dest=cdest, allow_community=True)
        assert rc == 0 and (cdest / "cpack" / "pack.yaml").is_file(), \
            f"--allow-community did not install the community pack (rc={rc})"
        odd = tmp / "odd"
        (odd / "x").mkdir(parents=True)
        (odd / "shelf.yaml").write_text("provenance: trusted-by-me\n", encoding="utf-8")
        reg_o = PackRegistry(odd)
        reg_o.discover()
        assert reg_o.errors and reg_o.provenance == "unlabelled", \
            "an unknown provenance label was accepted"
        assert PackRegistry(shelf).provenance == "unlabelled"
        if real_shelf.is_dir() and (real_shelf / "shelf.yaml").is_file():
            assert reg_real.provenance == "first-party", reg_real.provenance

        print("self-test: all commands work, refusals fire correctly, "
              "an empty shelf exits 2 rather than 0, and a community pack never "
              "installs without --allow-community")
        return 0

    except AssertionError as e:
        print(f"self-test assertion failed: {e}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve_shelf(env: dict | None = None, here: Path | None = None) -> Path:
    """Where the pack shelf lives.

    1. ``AWPACK_SHELF`` -- an explicit shelf (a clone, a mirror, a test dir).
    2. ``<package>/packs`` -- the shelf shipped INSIDE the wheel as package data.
    3. ``<package>/../packs`` -- a source checkout (``awpack/packs``).

    Before this, only (3) existed, so ``pip install awpack`` looked for
    ``site-packages/packs``, which no wheel contains, and ``awpack list`` said
    "no packs on the shelf" (w1b-19-05).
    """
    import os
    env = os.environ if env is None else env
    explicit = (env.get("AWPACK_SHELF") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    pkg = (here or Path(__file__).resolve().parent)
    bundled = pkg / "packs"
    if bundled.is_dir():
        return bundled
    return pkg.parent / "packs"


def _parse(argv: list[str]) -> tuple[list[str], dict]:
    """Split argv into positionals and the flags this CLI knows."""
    pos: list[str] = []
    opts: dict = {"json": False, "dest": None, "ref": None, "replace": False,
                  "allow_community": False}
    it = iter(argv)
    for a in it:
        if a == "--json":
            opts["json"] = True
        elif a == "--replace":
            opts["replace"] = True
        elif a == "--allow-community":
            opts["allow_community"] = True
        elif a in ("--dest", "--ref"):
            val = next(it, None)
            if val is None:
                raise ValueError(f"{a} needs a value")
            opts[a[2:]] = val
        elif a.startswith("--dest="):
            opts["dest"] = a.split("=", 1)[1]
        elif a.startswith("--ref="):
            opts["ref"] = a.split("=", 1)[1]
        else:
            pos.append(a)
    return pos, opts


def main(argv: list[str] | None = None, shelf: Path | None = None) -> int:
    """Main entry point."""
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return _self_test()
    if "--list-verbs" in argv:
        for verb in VERBS:
            print(verb)
        return 0
    try:
        pos, opts = _parse(argv)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    if not pos:
        print("usage: awpack {list,show,install,verify,remove} [id] "
              "[--dest DIR] [--json]", file=sys.stderr)
        return 1

    registry = PackRegistry(shelf or resolve_shelf())
    registry.discover()

    cmd, rest = pos[0], pos[1:]
    as_json, dest = opts["json"], opts["dest"]
    if cmd == "list":
        return cmd_list(registry, as_json=as_json)
    if cmd not in VERBS:
        print(f"unknown command: {cmd!r}", file=sys.stderr)
        return 1
    if not rest:
        print(f"usage: awpack {cmd} <pack-id>", file=sys.stderr)
        return 1
    if cmd == "show":
        return cmd_show(registry, rest[0])
    if cmd == "install":
        return cmd_install(registry, rest[0], dest=dest, as_json=as_json,
                           replace=opts["replace"],
                           allow_community=opts["allow_community"])
    if cmd == "verify":
        return cmd_verify(registry, rest[0], dest=dest, as_json=as_json)
    return cmd_remove(registry, rest[0], dest=dest, as_json=as_json)


if __name__ == "__main__":
    raise SystemExit(main())
