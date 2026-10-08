"""Client for the AnyPS5 Aither bridge -- agents watch frames and drive the pad of a relinked title.

AnyPS5 (GPL-2.0-only) runs as its own process; this module speaks only its wire protocol
(docs/user/AITHER_BRIDGE.md in github.com/wizzense/AnyPS5) and carries none of its code.
Start the title with ``APS5_AGENT_BRIDGE=<port>`` and connect here. Issue #12274.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, field

PROTO = 1

# Pad::PadButton bits (the protocol's button mask).
BUTTONS = {
    "l3": 0x0002, "r3": 0x0004, "options": 0x0008,
    "up": 0x0010, "right": 0x0020, "down": 0x0040, "left": 0x0080,
    "l2": 0x0100, "r2": 0x0200, "l1": 0x0400, "r1": 0x0800,
    "triangle": 0x1000, "circle": 0x2000, "cross": 0x4000, "square": 0x8000,
    "touchpad": 0x100000,
}


@dataclass(frozen=True)
class Frame:
    n: int
    w: int
    h: int
    buf: int
    ts_us: int


@dataclass
class PadState:
    buttons: tuple[str, ...] = ()
    lx: int = 128
    ly: int = 128
    rx: int = 128
    ry: int = 128
    l2: int = 0
    r2: int = 0

    def command(self) -> str:
        mask = 0
        for name in self.buttons:
            if name not in BUTTONS:
                raise ValueError(f"unknown button {name!r}; known: {sorted(BUTTONS)}")
            mask |= BUTTONS[name]
        axes = (self.lx, self.ly, self.rx, self.ry, self.l2, self.r2)
        for value in axes:
            if not 0 <= int(value) <= 255:
                raise ValueError(f"axis value {value} outside 0..255")
        return "pad " + " ".join(str(int(v)) for v in (mask, *axes)) + "\n"


class BridgeError(RuntimeError):
    pass


@dataclass
class PS5Bridge:
    """One connection to a running title. Not thread-safe; one agent drives one pad."""

    port: int
    host: str = "127.0.0.1"
    timeout_s: float = 5.0
    _sock: socket.socket | None = field(default=None, repr=False)
    _buf: bytes = field(default=b"", repr=False)
    errors: list[str] = field(default_factory=list)

    def connect(self) -> PS5Bridge:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        hello = self._read_event()
        if hello.get("t") != "hello" or hello.get("proto") != PROTO:
            self.close()
            raise BridgeError(f"unexpected hello {hello!r} (want proto {PROTO})")
        return self

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def __enter__(self) -> PS5Bridge:
        return self.connect() if self._sock is None else self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _read_event(self) -> dict:
        if self._sock is None:
            raise BridgeError("not connected")
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(4096)
            except OSError as exc:
                raise BridgeError(f"title closed the bridge ({exc})") from exc
            if not chunk:
                raise BridgeError("title closed the bridge")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise BridgeError(f"malformed bridge line {line[:80]!r}") from exc

    def next_frame(self) -> Frame:
        """Block until the next completed flip. Error lines are kept in ``errors``."""
        while True:
            event = self._read_event()
            kind = event.get("t")
            if kind == "frame":
                return Frame(int(event["n"]), int(event["w"]), int(event["h"]),
                             int(event["buf"]), int(event["ts_us"]))
            if kind == "error":
                self.errors.append(str(event.get("msg", "")))
                continue
            raise BridgeError(f"unexpected bridge event {event!r}")

    def _send(self, text: str) -> None:
        if self._sock is None:
            raise BridgeError("not connected")
        try:
            self._sock.sendall(text.encode("ascii"))
        except OSError as exc:
            raise BridgeError(f"title closed the bridge ({exc})") from exc

    def press(self, state: PadState) -> None:
        self._send(state.command())

    def release(self) -> None:
        self._send("release\n")

    def step(self, state: PadState, frames: int = 1) -> Frame:
        """Hold ``state`` for ``frames`` flips, release, and return the last frame seen."""
        if frames < 1:
            raise ValueError("frames must be >= 1")
        self.press(state)
        frame = self.next_frame()
        for _ in range(frames - 1):
            frame = self.next_frame()
        self.release()
        return frame

    def measure_fps(self, seconds: float = 2.0) -> float:
        """Frame events per second over a window, timed by the title's own clock."""
        first = self.next_frame()
        last = first
        deadline = time.monotonic() + seconds
        count = 0
        while time.monotonic() < deadline:
            last = self.next_frame()
            count += 1
        elapsed_us = last.ts_us - first.ts_us
        return count * 1_000_000 / elapsed_us if elapsed_us > 0 else 0.0
