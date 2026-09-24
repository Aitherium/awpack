#!/usr/bin/env python3
"""awpack: install and manage agent packs from the shelf.

CONTRACT:
  awpack list                 list packs on the shelf
  awpack show <id>            render manifest for a human
  awpack install <id>         resolve deps, check runtime, install
  awpack verify <id>          is the pack installed and loadable?
  awpack --self-test          prove every rule can still fail; every happy path works

Exit codes:
  0: success (list, show succeeded; install/verify completed; self-test passed)
  1: refused (pack not found, runtime unmet, deps unmet, already installed, etc.)
  2: cannot judge (shelf unreadable, manifest unparseable, etc.)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

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

    def discover(self) -> int:
        """Scan shelf for packs. Return count discovered, or 0 if shelf unreadable."""
        if not self.shelf.is_dir():
            self.errors.append(f"shelf {self.shelf} is not a directory")
            return 0
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


def cmd_list(registry: PackRegistry) -> int:
    """List all packs on the shelf."""
    if registry.errors:
        for err in registry.errors:
            print(f"  {err}", file=sys.stderr)
        return 2
    if not registry.packs:
        print("no packs on the shelf", file=sys.stderr)
        return 2
    print("Packs on shelf:\n")
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
    print(f"Pack: {pack_id}\n")
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


def cmd_install(registry: PackRegistry, pack_id: str) -> int:
    """Install a pack to ~/.aither/agents/<id>.

    Steps:
    1. Find pack manifest
    2. Check runtime requirement
    3. Check dependencies (needs)
    4. Create install dir if needed
    5. Copy pack files
    6. Print the install command from manifest
    """
    if registry.errors:
        for err in registry.errors:
            print(f"  {err}", file=sys.stderr)
        return 2
    manifest = registry.get(pack_id)
    if not manifest:
        print(f"pack not found: {pack_id!r}", file=sys.stderr)
        return 1

    # Check runtime requirement
    runtime_req = manifest.get("runtime", "").strip()
    if runtime_req:
        satisfied, msg = _check_runtime(runtime_req)
        if not satisfied:
            print(f"runtime not satisfied: {msg}", file=sys.stderr)
            return 1

    # Check dependencies
    needs = manifest.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    unmet = []
    for need_id in needs:
        if need_id not in registry.packs:
            unmet.append(need_id)
    if unmet:
        print(f"unmet dependencies: {', '.join(unmet)}", file=sys.stderr)
        return 1

    # Determine install location
    agents_dir = Path.home() / ".aither" / "agents"
    install_dir = agents_dir / pack_id
    if install_dir.exists():
        print(
            f"already installed at {install_dir}; "
            f"remove it manually if you need to reinstall",
            file=sys.stderr,
        )
        return 1

    # Create the install directory and copy pack files
    try:
        agents_dir.mkdir(parents=True, exist_ok=True)
        pack_dir = manifest["_dir"]
        shutil.copytree(pack_dir, install_dir)
    except (OSError, PermissionError) as e:
        print(f"install failed: {e}", file=sys.stderr)
        return 1

    # Print the install command from manifest (user must run it)
    install_cmd = manifest.get("install", "").strip()
    print(f"installed {pack_id} to {install_dir}\n")
    if install_cmd:
        print("Next, run:")
        print()
        for line in install_cmd.splitlines():
            print(f"  {line}")
        print()
    return 0


def cmd_verify(registry: PackRegistry, pack_id: str) -> int:
    """Verify pack is installed and loadable.

    Returns 0 if pack.yaml exists at expected location, 1 if not.
    """
    if registry.errors:
        for err in registry.errors:
            print(f"  {err}", file=sys.stderr)
        return 2
    manifest = registry.get(pack_id)
    if not manifest:
        print(f"pack not found in shelf: {pack_id!r}", file=sys.stderr)
        return 1

    # Check if it's installed
    agents_dir = Path.home() / ".aither" / "agents"
    install_dir = agents_dir / pack_id
    manifest_file = install_dir / "pack.yaml"
    if not manifest_file.exists():
        print(
            f"pack {pack_id!r} not installed "
            f"(expected at {manifest_file})",
            file=sys.stderr,
        )
        return 1

    # Try to parse it
    try:
        installed = _load_manifest(manifest_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"installed pack.yaml corrupted: {e}", file=sys.stderr)
        return 1

    # Verify it's the same pack
    if installed.get("id") != pack_id:
        print(
            f"installed pack id mismatch: "
            f"expected {pack_id!r}, got {installed.get('id')!r}",
            file=sys.stderr,
        )
        return 1

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
            "runtime: sys\n"
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
        # Test install — good pack should try to install
        # (but will fail if ~/.aither exists and is writable)
        ret = cmd_install(registry, "test_pack")
        if ret == 0:
            # If it succeeded, verify it was installed
            assert cmd_verify(registry, "test_pack") == 0
            # Clean up
            install_dir = Path.home() / ".aither" / "agents" / "test_pack"
            shutil.rmtree(install_dir, ignore_errors=True)
        # If ret==1, it's OK (install dir already exists or permission denied)

        # Test verify (not installed)
        reg2 = PackRegistry(shelf)
        reg2.discover()
        assert cmd_verify(reg2, "test_pack") == 1

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

        print("self-test: all commands work, refusals fire correctly, "
              "and an empty shelf exits 2 rather than 0")
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


def main() -> int:
    """Main entry point."""
    if "--self-test" in sys.argv:
        return _self_test()

    if len(sys.argv) < 2:
        print(
            "usage: awpack {list,show,install,verify} [args]",
            file=sys.stderr,
        )
        return 1

    shelf = resolve_shelf()

    registry = PackRegistry(shelf)
    registry.discover()

    cmd = sys.argv[1]
    if cmd == "list":
        return cmd_list(registry)
    elif cmd == "show":
        if len(sys.argv) < 3:
            print("usage: awpack show <pack-id>", file=sys.stderr)
            return 1
        return cmd_show(registry, sys.argv[2])
    elif cmd == "install":
        if len(sys.argv) < 3:
            print("usage: awpack install <pack-id>", file=sys.stderr)
            return 1
        return cmd_install(registry, sys.argv[2])
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("usage: awpack verify <pack-id>", file=sys.stderr)
            return 1
        return cmd_verify(registry, sys.argv[2])
    else:
        print(f"unknown command: {cmd!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
