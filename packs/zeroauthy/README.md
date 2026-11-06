# zeroauthy

An identity provider for your own machine: sign-in, OIDC, MFA, social and
enterprise connections — a clean-room, Apache-2.0 alternative to a hosted auth
vendor.

**This pack is not zeroauthy.** zeroauthy is built and released by the
[OccupySaaS](https://occupysaas.com) community at
[github.com/occupysaas/zeroauthy](https://github.com/occupysaas/zeroauthy).
The pack exists so the product has a shelf entry here, with commands that were
checked against their README rather than invented.

## What you get

`awpack install zeroauthy` copies this directory to `~/.aither/agents/zeroauthy/`.
It does not download, build or run anything. The `install:` block in
`pack.yaml` is the runbook; follow it.

- Source and docs: their repo, Apache-2.0.
- Image: `ghcr.io/occupysaas/zeroauthy:1.0.0-rc.1` (public).
- Also published: release binaries for linux/amd64, linux/arm64 and
  darwin/arm64, with a `SHA256SUMS` file.

## Before you run it

The server will not start without a TLS certificate pair and a master key.
Their `docs/quickstart.md` covers both. The run command in `pack.yaml` assumes
`certs/cert.pem`, `certs/key.pem` and `master.key` relative to your working
directory.

## Status

`preview`. The upstream release is `v1.0.0-rc.1`, a prerelease. Their
[compatibility matrix](https://github.com/occupysaas/zeroauthy/blob/main/docs/compat/matrix.md)
lists what is and is not covered.

## What this pack does not do

- It does not vendor their code, host their service, or grant any trademark
  right. `AitherOS/config/orgs/occupysaas.yaml` records that boundary under
  `not_offered`.
- It declares no tools. Their admin CLI and management API exist; wrapping them
  is separate work, and a pack must never advertise a tool that binds to
  nothing.
