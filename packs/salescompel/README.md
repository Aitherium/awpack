# salescompel

An open-source Salesforce replacement, early but real.

SalesCompel is a Go/PostgreSQL candidate with a Vue record workflow, OAuth
authorization code with PKCE, and a compatibility laboratory that measures how
much of the Salesforce surface it actually reproduces. It is Apache-2.0.

**This pack is not SalesCompel.** It is built by the
[OccupySaaS](https://occupysaas.com) community at
[github.com/occupysaas/salescompel](https://github.com/occupysaas/salescompel).
The pack records how to build and run it, checked against the source.

## Status, honestly

There is **no published container image and no release tag** — the project is
source only. Build it. Their compatibility matrix records what is and is not
implemented, and certification against Salesforce is explicitly not claimed.

## Run it

```bash
git clone https://github.com/occupysaas/salescompel
cd salescompel
go build -o salescompel ./cmd/salescompel
```

It needs PostgreSQL, and it keeps **two database principals separate**:

| Variable | Used by | Principal |
|---|---|---|
| `MIGRATION_DATABASE_URL` | `migrate`, `schema`, `user`, `oauth-app`, `provision` | operator |
| `DATABASE_URL` | `serve` — records | runtime |
| `AUTH_DATABASE_URL` | `serve` — identity | runtime |

`serve` opens the runtime principal and refuses owner privileges. That split is
deliberate: the process serving requests should not be able to reshape the
schema.

Nothing upstream creates the database, the logins or the grants. The names below
are examples you choose.

```bash
createdb salescompel
psql -d salescompel -c "CREATE ROLE salescompel_op  LOGIN PASSWORD 'change-me';"
psql -d salescompel -c "CREATE ROLE salescompel_app LOGIN PASSWORD 'change-me';"
psql -d salescompel -c "CREATE ROLE salescompel_id  LOGIN PASSWORD 'change-me';"

export MIGRATION_DATABASE_URL='postgres://salescompel_op@127.0.0.1:5432/salescompel?sslmode=disable'
export DATABASE_URL='postgres://salescompel_app@127.0.0.1:5432/salescompel?sslmode=disable'
export AUTH_DATABASE_URL='postgres://salescompel_id@127.0.0.1:5432/salescompel?sslmode=disable'

./salescompel migrate status
./salescompel migrate up

SALESCOMPEL_TENANT=acme SALESCOMPEL_USERNAME=admin@example.com \
  SALESCOMPEL_PASSWORD='choose-one' SALESCOMPEL_ROLE=owner \
  ./salescompel user create

./salescompel serve -addr 127.0.0.1:8080
```

## Traps

- **Migrations are forward-only and never run at startup.** Run
  `migrate status`, then `migrate up`, as a separate step. A server that
  migrates itself on boot is a server you cannot roll back.
- **A non-loopback listener is refused without TLS.** `-addr 0.0.0.0:8443`
  needs `-tls-cert` and `-tls-key`; both or neither.
- **The UI is built assets, not source.** `-assets` defaults to `web/dist`.
  Build them once with Node 22.12+ (`cd web && npm ci && npm run build`), or
  pass `-assets ""` to serve the API alone.
- **`user create` reads environment variables**, not flags — the four
  `SALESCOMPEL_*` values above.
- **The compatibility laboratory is the truth about coverage**, not the README's
  ambition. Read it before promising a Salesforce migration.

## What this pack does not do

It does not vendor their code, host their service, or grant any trademark right.
It declares no tools: SalesCompel exposes a REST API and a Go CLI, and wrapping
that is separate work.
