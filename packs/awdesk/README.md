# awdesk

The desktop companion.

awdesk puts the agent on your desk: a tray icon, an avatar, and a decision card
that pops when it needs you rather than leaving a question buried in a
transcript. It is a client — it talks to a daemon; it does not serve tools
itself.

Source: [github.com/Aitherium/awdesk](https://github.com/Aitherium/awdesk)

## Install

Download the asset for your platform from the
[releases page](https://github.com/Aitherium/awdesk/releases). As of `v0.1.28`:

| Platform | Asset |
|---|---|
| Windows x64 | `Desk-0.1.28-windows-x64-setup.exe` |
| macOS arm64 | `Desk-0.1.28-macos-arm64.dmg` (or `.zip`) |
| macOS x64 | `Desk-0.1.28-macos-x64.dmg` (or `.zip`) |
| Linux x64 | `Desk-0.1.28-linux-amd64.deb`, `-linux-x86_64.AppImage` |

Every release carries `SHA256SUMS.txt`. Check the download against it.

From source:

```bash
git clone https://github.com/Aitherium/awdesk
cd awdesk
npm install && npx electron .
```

## Traps

- **A tray app that shows nothing is usually a daemon that is not there.** Check
  the process it talks to before reinstalling the app.
- **Decision cards need somewhere to come from.** If no daemon is connected, the
  desk is decoration.
- **Do not run the source build and an installed copy at once.** Two tray icons,
  two bridges, and it is rarely obvious which one answered.
- **The installer is unsigned on some channels.** Verify the SHA256 rather than
  clicking through a warning.

## What this pack does not do

It declares no tools. The desk is the surface a person sees; the capabilities
behind it belong to the daemon.
