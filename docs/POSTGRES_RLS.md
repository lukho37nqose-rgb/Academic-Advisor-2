# PostgreSQL Row-Level Security

## Security boundary

Production serving credentials must not be PostgreSQL superusers and must not
hold `BYPASSRLS`. Migration credentials, serving credentials, and any emergency
database access are separate accounts with separate secrets and audit trails.

Migration `c8f4a2d7e613` enables and **forces** row-level security on every
tenant-bearing table and on the relational chains that do not carry a tenant
column themselves:

- domains, releases, and compiled rule graphs;
- handbook uploads, pages, OCR proposals, and OCR audit events;
- policy drafts, ambiguity records, metadata audit records, and release data;
- system-record mapping configurations and their append-only review events;
- evidence, claims, facts, reasoning graphs, decision-review records, and
  support casework.

The application writes `ire.tenant_id` and `ire.access_mode` with PostgreSQL
`set_config(..., true)` whenever a transaction begins. The values are
transaction-local and are restored after every repository commit, which avoids
connection-pool leakage between institutions. If a tenant context is absent,
tenant policies return no rows and reject writes.

Public policy-guide routes have a distinct `public` mode. It may read only a
domain that explicitly enables its public guide, its approved releases, and its
compiled guide graph. It can create an initial assistance request only when the
domain explicitly enables assistance. It cannot read support requests, evidence,
claims, facts, cases, or traces.

For that public write, the API creates an unpredictable request ID and scopes it
into the transaction. RLS permits only that exact request and its first audit
event; a generic public database transaction cannot add an event to an existing
case.

## Deployment roles

Use institution-managed secrets and roles equivalent to:

| Role | Purpose | Constraint |
| --- | --- | --- |
| `ire_migrator` | Reviewed Alembic schema changes | Separate credential; no application traffic. |
| `ire_app` | API and tenant-scoped workers | `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEROLE`, `NOCREATEDB`; only DML rights needed by the application. |
| `ire_break_glass` | Approved incident response | Disabled by default, time-limited, separately logged, never used by the API. |

The migration owner must use `FORCE ROW LEVEL SECURITY`; table ownership alone
must not let the serving account evade a policy. Production startup queries
PostgreSQL catalog metadata and refuses to serve when any protected table lacks
enabled and forced RLS, or when the connected role is superuser or `BYPASSRLS`.

The migration principal must grant the serving role access to the RLS helper
schema without making it its owner:

```sql
GRANT USAGE ON SCHEMA ire TO ire_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ire TO ire_app;
```

Use the institution's actual serving-role name in place of `ire_app`; grant
schema and function access explicitly rather than relying on PostgreSQL's
default `PUBLIC` function privilege.

## Workers and retention

Trusted handbook and OCR job payloads must include `tenant_id`. The production
worker CLI accepts `--tenant-id`; missing tenant context fails instead of using a
cross-tenant queue query. Retention work runs once per configured tenant through
`IRE_RETENTION_TENANT_IDS`, or through an institution-managed scheduler that
supplies the same explicit scope.

## Verification before traffic

1. Apply the migration with `ire_migrator`.
2. Connect as `ire_app`; confirm it is neither superuser nor `BYPASSRLS`.
3. Create records for two test tenants and prove that a transaction scoped to
   one tenant cannot select, update, or insert against the other.
4. Confirm a public session can see only an explicitly published guide and
   cannot read any personal or casework table.
5. Rehearse a worker and retention job with a tenant-scoped payload.

The repository includes this as an executable integration rehearsal. See
[POSTGRES_RLS_REHEARSAL.md](POSTGRES_RLS_REHEARSAL.md) for the disposable
database contract, local Docker command, and CI coverage.

RLS is a strong defence against missed application filters and accidental raw
queries. It does not turn a fully compromised application credential into a
tenant-proof trust root, because that credential can set the tenant context.
Institutions needing that stronger boundary should use isolated databases,
tenant-specific database credentials, or a separately authenticated data access
service.
