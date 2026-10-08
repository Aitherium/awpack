# ruff: noqa: N999 -- the directory name IS the pack id (ps5-bridge); it loads by file path
"""ps5-bridge tool pack -- an agent watches frames from and drives the pad of a relinked PS5 title.

The title runs in its own process: AnyPS5 (GPL-2.0-only) with its Aither bridge
(github.com/wizzense/AnyPS5 PR #1), started with ``APS5_AGENT_BRIDGE=<port>``.
This pack carries only our client (``ps5_bridge.py``, byte-identical to
``AitherOS/lib/worldrunner/ps5_bridge.py``) and speaks the wire protocol.

    ps5_connect     attach to a title's bridge port
    ps5_frame       wait for the next completed frame
    ps5_press       hold buttons/sticks for N frames, then release
    ps5_fps         frame rate from the title's own clock
    ps5_disconnect  detach (the title releases the pad)
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("awpack.ps5_bridge")

DEFAULT_PORT = 47500


def _client_module():
    name = "awpack_ps5_bridge_client"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("ps5_bridge.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_client = _client_module()
_sessions: dict = {}


def _fail(exc: Exception) -> dict:
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _session(port: int):
    bridge = _sessions.get(port)
    if bridge is None:
        raise _client.BridgeError(f"not connected to port {port}: call ps5_connect first")
    return bridge


def _frame(frame) -> dict:
    return {"n": frame.n, "w": frame.w, "h": frame.h, "buf": frame.buf, "ts_us": frame.ts_us}


def ps5_connect(port: int = DEFAULT_PORT) -> dict:
    """Attach to a running relinked PS5 title (started with APS5_AGENT_BRIDGE=<port>)."""
    try:
        if port in _sessions:
            return {"ok": True, "port": port, "already": True}
        _sessions[port] = _client.PS5Bridge(int(port)).connect()
        return {"ok": True, "port": port}
    except Exception as exc:  # noqa: BLE001 - surface the failure to the agent
        return _fail(exc)


def ps5_frame(port: int = DEFAULT_PORT) -> dict:
    """Wait for the title's next completed frame: flip count, size and timestamp."""
    try:
        return {"ok": True, "frame": _frame(_session(port).next_frame())}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


def ps5_press(buttons: Any = (), frames: int = 1, lx: int = 128, ly: int = 128,
              rx: int = 128, ry: int = 128, l2: int = 0, r2: int = 0,
              port: int = DEFAULT_PORT) -> dict:
    """Hold buttons (["cross"] or "cross,r1") and sticks (0-255, centre 128) for N frames.

    Buttons: cross circle square triangle up down left right l1 r1 l2 r2 l3 r3 options
    touchpad. The pad is released after the last frame.
    """
    try:
        if isinstance(buttons, str):
            names = [b.strip() for b in buttons.split(",")]
        else:
            names = list(buttons)
        state = _client.PadState(tuple(n for n in names if n), lx, ly, rx, ry, l2, r2)
        frame = _session(port).step(state, frames=int(frames))
        return {"ok": True, "held_frames": int(frames), "last_frame": _frame(frame)}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


def ps5_fps(seconds: float = 2.0, port: int = DEFAULT_PORT) -> dict:
    """Measure the title's frame rate over a window, timed by the title's own clock."""
    try:
        return {"ok": True, "fps": round(_session(port).measure_fps(float(seconds)), 2)}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


def ps5_disconnect(port: int = DEFAULT_PORT) -> dict:
    """Detach from the title; the bridge releases any held buttons."""
    bridge = _sessions.pop(port, None)
    if bridge is not None:
        bridge.close()
    return {"ok": True, "was_connected": bridge is not None}


TOOLS = (ps5_connect, ps5_frame, ps5_press, ps5_fps, ps5_disconnect)
_ACTION_CLASS = {"ps5_frame": "read", "ps5_fps": "read"}


def register(registry: Any) -> int:
    """Register the five ps5 tools on an adk ToolRegistry. Returns the count."""
    n = 0
    for fn in TOOLS:
        try:
            registry.register(fn, name=fn.__name__, description=(fn.__doc__ or "").strip(),
                              action_class=_ACTION_CLASS.get(fn.__name__, "write"))
            n += 1
        except Exception as exc:  # noqa: BLE001 - a registry refusal must not kill agent boot
            logger.warning("ps5-bridge: could not register %s (%s)", fn.__name__, exc)
    return n
