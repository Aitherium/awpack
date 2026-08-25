# persona

Desktop avatar bridge for Persona. Use adk agents to control a VRM avatar running
on your local machine — drive animations, voice, character switching, and audio settings.

## What it does

Persona is a standalone desktop application that renders and animates a 3D VRM avatar.
This pack provides tools for adk agents (running on the same machine) to control that
avatar in real time:

- **persona_status** — Check if the avatar is running and responsive
- **persona_animate** — Play an animation (built-in animations or custom .vrma files)
- **persona_set_character** — Switch to a different avatar character
- **persona_speak_state** — Set the avatar's activity state (idle, talking, etc.)
- **persona_audio_level** — Adjust microphone or speaker audio levels
- **persona_mute_microphone** — Mute/unmute voice input
- **persona_mute_output** — Mute/unmute voice output

## Requirements

- **Persona desktop app** — Download from [https://github.com/xikhar/persona](https://github.com/xikhar/persona)
  and run it on the same machine where you run adk agents.
- **adk** — This pack's tools are available through adk when Persona is running.
- **Host-run only** — Persona tools connect to `http://127.0.0.1:47831` (loopback).
  Containerized agents cannot reach it without a host relay (tunneling support is 
  a roadmap item). Run adk agents on the host machine, not in containers.

## Getting started

1. **Install Persona** (one time):
   ```bash
   # Clone or download Persona
   git clone https://github.com/xikhar/persona
   cd persona
   # Follow its README to build and run
   ```

2. **Run Persona** on your desktop.

3. **Use adk with Persona tools**:
   ```bash
   # Persona is auto-enabled when running (ADK_PERSONA=1 by default)
   adk <your-command>  # Your agent can now use persona_* tools
   
   # To disable: ADK_PERSONA=0 adk <your-command>
   ```

## Notes

- **Graceful degradation**: If Persona is not running or the bridge port is unavailable,
  the tools report what happened and return no-op responses. Agents continue working.
- **Desktop-specific**: Persona is a host-run desktop application. Containerized agents
  cannot use it directly (network bridge or SSH relay would be required).
- **Loopback only**: The bridge is deliberately restricted to `127.0.0.1:47831` for
  security. It does not expose the avatar to the network.
- **Fire-and-forget**: Tool calls are non-blocking; if Persona is unresponsive, the
  call silently fails and the agent moves on.

## Licensing

Persona (the avatar engine) is created by [xikhar](https://github.com/xikhar) and licensed
under the MIT License. This pack is not affiliated with or endorsed by Persona's author.
It is a bridge from adk agents to the Persona application.
