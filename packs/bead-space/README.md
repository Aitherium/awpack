# bead-space

Agent companion for BeadSpace: an interactive D3 work graph visualized as a tiny
universe. This pack provides system prompting and integration for adk agents that
assist users working with BeadSpace.

## What it does

BeadSpace is a visual work-tracking tool that renders tasks, projects, and
relationships as an interactive 3D space. This pack prepares adk agents to
understand and help with BeadSpace use: discussing the graph structure, suggesting
connections, and explaining the work landscape.

The pack does not expose BeadSpace API calls as tools yet — it is a brain pack
that grounds the agent's understanding of the work-graph domain.

## Requirements

- **BeadSpace** — Get it from [https://github.com/wbern/bead-space](https://github.com/wbern/bead-space)
  or the live version at [https://pages.bernting.se/bead-space/](https://pages.bernting.se/bead-space/)
- **adk** — This pack provides agent support for BeadSpace-related tasks

## Getting started

1. **Open BeadSpace** in your browser or run it locally.

2. **Use adk agents** to discuss your work graph:
   ```bash
   adk <your-command>  # Agent is now aware of BeadSpace concepts
   ```

3. **Ask your agent** questions about your tasks, connections, and the work universe.

## Notes

- **Brain pack** — This is agent system-prompting only. No BeadSpace API calls are
  exposed yet. Future versions may add tools for reading/writing the graph.
- **Conceptual** — The agent understands the work-graph as a visual, spatial domain
  with hierarchical relationships. It asks clarifying questions about structure
  rather than assuming linear task lists.
- **Local-first** — BeadSpace is designed for personal use. The companion agent
  is correspondingly scoped to local work tracking.

## Licensing

BeadSpace is created by [wbern](https://github.com/wbern) and licensed under the
MIT License. This pack is not affiliated with or endorsed by BeadSpace's author.
It provides adk agent integration for users of BeadSpace.
