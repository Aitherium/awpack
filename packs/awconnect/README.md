# awconnect

The browser half of the stack.

awconnect hands an agent the page you are looking at, and gives you a menu to
act on it, without you copying and pasting. It pairs over loopback to a local
daemon; when no daemon answers it falls back to the cloud, and says so.

- Extension: [Chrome Web Store](https://chromewebstore.google.com/detail/awconnect/peeojgjhjficedkncdejbfnacooodbak)
- Source (MIT): [github.com/Aitherium/AitherConnect](https://github.com/Aitherium/AitherConnect)
- Current manifest version: `3.9.0`

Note the naming: the tree in this repository is `awconnect/`; the public mirror
is `AitherConnect`. Same extension.

## Install

Install from the store, or load unpacked from a checkout of `awconnect/` if you
want your own build.

Then start a local daemon **before** expecting it to pair:

```bash
awnode mcp        # a local gateway
# or the awsh harness on :8362
```

## Traps

- **"No awdk daemon answered …; using Cloud" means exactly that.** The extension
  is working, and your pages are going somewhere other than your machine. If you
  wanted local, start the daemon.
- **A page shared is a page shared.** Whatever the agent can read here, it can
  read — including anything on screen that is not part of the task.
- **Chrome and Edge are different stores.** Installing for one does not cover the
  other.

## What this pack does not do

It declares no tools. awconnect is a client surface; the capabilities behind it
belong to the daemon it pairs with.
