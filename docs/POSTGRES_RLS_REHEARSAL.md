# PostgreSQL RLS Rehearsal

## What it proves

`python tools/run_postgres_rls_rehearsal.py` is the local PostgreSQL security
verification command. It starts the pinned disposable PostgreSQL service,
checks that Alembic has exactly one head, and then runs
`tests/integration/test_postgres_rls.py`. The test is a real PostgreSQL test,
not a SQLite approximation. It creates separate migration and serving roles,
applies the full Alembic chain as the migration role, and verifies that the
serving role:

- is not superuser, `BYPASSRLS`, `CREATEROLE`, or `CREATEDB`;
- encounters enabled and forced RLS on every protected application table;
- can read its own tenant's draft and release data but cannot read, update, or
  insert another tenant's data;
- exposes only an explicitly public domain, release, and rule graph in public
  mode;
- can create only the server-scoped initial assistance request and event, while
  public sessions cannot read casework back;
- does not retain a previous tenant's transaction-local RLS context across
  pooled sessions; and
- cannot update or delete decision-bearing evidence, claims, facts, releases,
  rule graphs, or reasoning graphs through the runtime-style role.

The test uses the application's SQLAlchemy session event and context scopes,
so it also proves that production transaction setup reaches PostgreSQL rather
than only testing policy SQL in isolation. It also runs the production API's
database-startup RLS check against the serving credential.

## Safety contract

This rehearsal drops and recreates the `public` and `ire` schemas. It runs only
when all of these are true:

- `IRE_RLS_ALLOW_DESTRUCTIVE_REHEARSAL=confirmed`;
- all three URLs target a database named exactly `ire_rls_rehearsal`; and
- the migration and serving usernames both end in `_rehearsal` and differ.

Never point these variables at a UCT environment, a shared development
database, or a database containing institutional records.

## Local run

Run the full local rehearsal:

```powershell
python tools/run_postgres_rls_rehearsal.py
```

The command starts `docker-compose.rls.yml`, waits for PostgreSQL to accept
connections, confirms that Alembic has one head, runs the PostgreSQL RLS test
module, and removes the disposable volume afterwards.

If you need to inspect the database after a failed run:

```powershell
python tools/run_postgres_rls_rehearsal.py --keep-running
```

The bootstrap URL is used only to create controlled rehearsal roles, reset the
disposable schemas, and grant least-privilege access. Alembic runs through the
migrator URL. Every data assertion uses the serving URL.

To use an already-running disposable PostgreSQL service, set the three RLS URLs
and run:

```powershell
$env:IRE_RLS_ALLOW_DESTRUCTIVE_REHEARSAL = 'confirmed'
$env:IRE_RLS_BOOTSTRAP_URL = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/ire_rls_rehearsal'
$env:IRE_RLS_MIGRATOR_URL = 'postgresql+asyncpg://ire_migrator_rehearsal:migrator-rehearsal-password@127.0.0.1:5433/ire_rls_rehearsal'
$env:IRE_RLS_APP_URL = 'postgresql+asyncpg://ire_app_rehearsal:app-rehearsal-password@127.0.0.1:5433/ire_rls_rehearsal'
python tools/run_postgres_rls_rehearsal.py --no-compose
```

Remove the disposable database when finished:

```powershell
docker compose -f docker-compose.rls.yml down -v
```

Fast local and API tests may still use SQLite. SQLite runs do not prove RLS,
PostgreSQL JSONB semantics, PostgreSQL trigger behaviour, or the serving-role
catalog checks.

## Institution-managed rehearsal

Before UCT pilot traffic, UCT should provision a new empty database named
`ire_rls_rehearsal` and temporary roles such as `uct_ire_migrator_rehearsal`
and `uct_ire_app_rehearsal`. A UCT database administrator supplies three
time-limited URLs to the approved test operator, who runs the same test once.
The result, database-role statements, migration revision, and test output
should be retained with the pilot entry evidence. The temporary database and
roles should then be removed through UCT's change process.
