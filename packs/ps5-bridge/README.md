# ps5-bridge

Lets an adk agent **play a PS5 title**: it watches each completed frame and holds buttons
on the pad. The title is a PS5 executable you dumped from your own console and converted
with [AnyPS5](https://github.com/wizzense/AnyPS5) into a native Windows or Linux program.
Start it with the bridge switched on:

```bash
APS5_AGENT_BRIDGE=47500 ./app.elf      # or app.exe
```

## Tools

| tool | what it does |
|---|---|
| `ps5_connect(port=47500)` | attach to the title on `127.0.0.1:<port>` |
| `ps5_frame()` | wait for the next frame: flip count, width, height, timestamp |
| `ps5_press(buttons, frames=1, lx, ly, rx, ry, l2, r2)` | hold buttons and sticks for N frames, then release |
| `ps5_fps(seconds=2)` | measure the frame rate on the title's own clock |
| `ps5_disconnect()` | detach; the title releases any held buttons |

Buttons: `cross circle square triangle up down left right l1 r1 l2 r2 l3 r3 options touchpad`.
Sticks and triggers take values 0–255; sticks are centred at 128.

## What this pack is not

- **It does not include AnyPS5.** AnyPS5 is GPL-2.0-only and runs as its own process. This
  pack is only a client for the bridge's wire protocol (`docs/user/AITHER_BRIDGE.md` in the fork).
- **It does not include games, keys, or dump or decrypt tools.** You bring a title you own
  and dumped yourself.

## Getting started

```bash
pip install awdk
adk pack install ./awpack/packs/ps5-bridge
```

Then ask your agent to `ps5_connect`, check `ps5_fps`, and run `ps5_press(["cross"], frames=30)`.
