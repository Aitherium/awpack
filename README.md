# awpack — first-party agent packs

The packs we build, versioned and installable on their own.

## Why packs live here and not in the SDK

A pack bundled into the SDK inherits the SDK's licence and the SDK's release
cadence, and that is backwards in both directions:

- **A proprietary pack blocks the SDK's public publish.** This is measured, not
  theoretical: the SDK's sync gate aborts on exactly that and names the pack.
- **A good pack cannot ship a fix without an SDK release.** A one-line
  correction to a persona waits on a runtime release it has nothing to do with.

Packs and the runtime that loads them are different products with different
audiences. `awdk` is the runtime. This is the shelf.

A community marketplace is the layer *above* this: awpack is the first-party
shelf, the marketplace is everyone else's.

## What a pack is

A directory under `packs/<id>/` holding, at minimum:

```
packs/<id>/
  pack.yaml        # identity, version, what it needs, what it gives
  README.md        # what it does, for a stranger, in one screen
```

and optionally the agent identity, tool declarations, prompts and any data the
pack ships.

### `pack.yaml`

```yaml
id: gobbonet                  # directory name, and how it is installed
version: 0.1.0                # the pack's OWN version, not the SDK's
summary: >-                   # one sentence, no marketing
  Run GobboNet's chat on an agent loop, with campaign memory scoped by who
  knows what.
runtime: awdk>=3.7.0          # the runtime this pack loads into
needs: []                     # other packs, by id
extras: [memory]              # runtime extras the pack expects (pip extras)
tools: []                     # tool names the pack REGISTERS, if any
status: published             # published | preview | internal
licence: proprietary          # or a SPDX id — the SDK no longer decides this
```

**Every declared tool must exist.** A name in `tools:` is a promise: install
this pack and that tool is yours. One that binds to nothing is not a loud typo,
it is a capability the pack advertises and the runtime silently cannot provide,
so the agent behaves as though the feature is switched off.

**`status: internal` needs a reason.** A pack that must never be published is a
recorded decision, not an omission — write why in the README, or the next
person reads the absence as a backlog item and publishes it.

## Installing

```bash
git clone https://github.com/Aitherium/awpack
adk pack install ./awpack/packs/<id>      # or point your runtime at the dir
```

## What is here so far

| pack | status | what it is |
|---|---|---|
| `gobbonet` | preview | GobboNet's chat on an agent loop: campaign memory scoped by who knows what, plus character-card and lorebook import/export |

The rest of the first-party packs still live inside the SDK and move here one
at a time — a migration, not a bulk copy, because each one has to keep working
for the people already loading it.
