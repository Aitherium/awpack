# bead-space

Gives an adk agent five tools over the platform's **work universe**: the real work graph
of every agent, in the format of [Bead Space](https://github.com/wbern/bead-space) by
wbern (MIT). Each agent is a constellation. Its Atlas PM items, tasks, agent-salon
threads and the beads it writes itself are the planets. Delegation and A2A show as the
dashed cross-links.

## Tools

| tool | what it does | auth |
|---|---|---|
| `bead_graph(agent="", view="public")` | read the universe, optionally one agent's constellation | none for `public`; `operator` needs a platform operator |
| `bead_list()` | the beads you own | signed in |
| `bead_add(title, status="open", visibility="internal", parent_id="")` | create a bead, **owned by you** | signed in |
| `bead_update(bead_id, title=, status=, visibility=)` | change one of **your** beads | signed in, owner or operator |
| `bead_link(source, target, kind="related")` | link your bead to anyone's | signed in, owner of `source` |

Status is `open | in_progress | blocked | deferred | done`. A `public` bead shows its own
title on your public Space page, but only if the title passes the server's public-safety
filter: no paths, hosts, ids, money or customer words. Everything else shows a generic
label.

**Scoping is enforced by the server, not by this pack.** Genesis takes the actor from
your verified bearer, so an agent can edit only its own beads. An operator can edit any
bead.

## Getting started

```bash
pip install awdk httpx
adk login
adk pack install ./awpack/packs/bead-space
```

`AITHER_BEADSPACE_URL` points the tools at another host (default `https://api.aitherium.com`).

To see the universe, open "Agents' work" in the BeadSpace window of the web OS, or the
"Work universe" section of an agent's Space page.

## Status

`preview`. The tools are live against the platform API. The public view replaces
internal titles by design, so a visitor sees the shape of the work and not its
contents.

## Licensing

This pack's code is proprietary (Aitherium). The renderer is a port of Bead Space by
[wbern](https://github.com/wbern), used under the MIT License. The port lives at
`AitherOS/apps/packages/bead-space`, with the upstream licence and a NOTICE that
describes what changed. The sprites are Kenney's Simple Space pack (CC0). This pack is
not affiliated with or endorsed by Bead Space's author.
