# awnode

A gateway for the machine you own.

awnode sits in front of the hardware and model backends on one box and puts them
behind a single local endpoint, exposed as MCP tools an agent can call. It starts
without an account and serves locally; connecting it to a platform account is
opt-in.

MIT. Source: [github.com/Aitherium/awnode](https://github.com/Aitherium/awnode) ·
Docs: [aitherium.github.io/awnode](https://aitherium.github.io/awnode/)

## Run it

```bash
pip install awnode
awnode start          # local, auto-detected
awnode status
```

Point it at a backend explicitly when detection guesses wrong:

```bash
awnode start --local
awnode start --cloud
awnode start --vllm-url http://localhost:8120
```

Give an agent the read-only tool set:

```bash
awnode mcp
```

## Traps

- **`start` before `mcp`.** The tool surface is served by the running gateway;
  asking for tools with nothing started returns nothing useful.
- **`awnode connect` is a choice, not a setup step.** Without it the node still
  serves locally. With it, the node also answers to the control plane.
- **`--vllm-url` must reach the backend from inside the node's own network.**
  `localhost` there means the node's loopback, not your laptop's.
- **`awnode deploy` is a different job** from serving: it ships a service to a
  target (`--target docker --strategy rolling`). Do not read `start` as `deploy`.

## What this pack does not do

It declares no tools. The gateway's tool set is defined in the package itself;
read it with `awnode mcp` once running rather than trusting a list here.

It also ships no copy of the procedure in the public skills pack, on purpose:
awnode's own documentation travels with the brick, and a second copy would
drift away from it. This pack is the shelf entry; the brick is the manual.
