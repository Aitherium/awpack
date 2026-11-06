# aitherbrowser

An agent's own browser, running on your machine.

AitherBrowser is a headless Chromium that an agent drives directly: open a page,
look at what it actually renders, click and type, pull structured data out, and
remember a login so the next session does not start from nothing. Sessions,
screenshots, taught recipes and saved logins live in a volume on your disk.

## Status: does not install from PyPI yet

Three blockers, verified 2026-11-06. Read these before the commands.

1. **The addon manifest is not in the `awdk` wheel.** `adk addon enable
   aitherbrowser` raises `Unknown addon: aitherbrowser` on a pip-installed awdk.
   The command works inside a checkout of this repository, where the manifest
   resolves. It does not work from PyPI.
2. **The image is not publicly pullable.** `aitherium/aitheros-browser:latest`
   answers 404 on Docker Hub and 401 on GHCR anonymously, and the manager has no
   registry login step.
3. **`pilot_*` is not free.** It requires the PROFESSIONAL+ entitlement
   `can_use_computer_use`. And `adk addon enable` starts the container without
   loading any tool pack, so enabling the addon registers no tools by itself.

The commands below are correct where the manifest resolves.

## Run it

```bash
pip install awdk
adk addon enable aitherbrowser
curl -fsS http://127.0.0.1:8132/health
```

The addon manager starts the container (`aitherium/aitheros-browser`, port 8132),
waits for health, and records the endpoint. Once it is recorded, the agent's
browser calls go to **your** browser instead of the platform's — that handover is
the entire point of the addon, and without it a "self-hosted" browser is
decorative.

Managing it:

```bash
adk addon status aitherbrowser
adk addon logs aitherbrowser
adk addon disable aitherbrowser
```

## What the agent gets

- **Sessions** — open a URL with a goal, navigate, close out.
- **Perception** — the rendered page, its controls as structure, and a vision
  model you can ask about it.
- **Action** — click, type, scroll.
- **Extraction** — structured entities out of the page.
- **Memory** — a saved login for a domain, and a taught recipe written when a
  task completes so the next run starts further ahead.

## Entitlements

Self-hosting the container is free — it costs the platform nothing because it
runs on your hardware. Driving it is not: `pilot_*` needs `can_use_computer_use`
(PROFESSIONAL+) and the CRM/HAR tools need `can_use_untether`. Enabling the
addon locally does not change those gates.

## Running well

- **Give it memory.** A headless session with a couple of tabs sits near 1 GiB
  and spikes on a heavy page. The addon declares 2 GiB because under-declaring
  produces OOM kills that read as "the browser is flaky".
- **Keep `/dev/shm` at 512 MB.** The container default of 64 MB is the most
  common cause of silent renderer crashes under load; the addon sets this for
  you.
- **It is headless by default**, which is right for a server. A headful launch
  on a machine with no display fails with an error that names X11 rather than
  the real cause.
- **Do not recreate the container casually.** Saved logins and taught recipes
  live in the `aitherbrowser-profile` volume at `/app/data/browser`.

## Works without us

`offline_mode` is on: the browser does not need the platform's control plane to
open a tab. A browser that phones home to work is not self-hosted.
