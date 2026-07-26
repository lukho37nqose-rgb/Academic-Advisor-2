# PostgreSQL RLS Rehearsal

## What it proves

`tests/integration/test_postgres_rls.py` is a real PostgreSQL test, not a
SQLite approximation. It creates separate migration and serving roles, applies
the full Alembic chain as the migration role, and verifies that the serving
role:

- is not superuser, `BYPASSRLS`, `CREATEROLE`, or `CREATEDB`;
- encounters enabled and forced RLS on every protected application table;
- can read its own tenant's draft and release data but cannot read, update, or
  insert another tenant's data;
- exposes only an explicitly public domain, release, and rule graph in public
  mode; and
- can create only the server-scoped initial assistance request and event, while
  public sessions cannot read casework back.

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

Start the isolated database:

```powershell
docker compose -f docker-compose.rls.yml up -d
```

Run the rehearsal in PowerShell:

```powershell
$env:IRE_RLS_ALLOW_DESTRUCTIVE_REHEARSAL = 'confirmed'
$env:IRE_RLS_BOOTSTRAP_URL = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/ire_rls_rehearsal'
$env:IRE_RLS_MIGRATOR_URL = 'postgresql+asyncpg://ire_migrator_rehearsal:migrator-rehearsal-password@127.0.0.1:5433/ire_rls_rehearsal'
$env:IRE_RLS_APP_URL = 'postgresql+asyncpg://ire_app_rehearsal:app-rehearsal-password@127.0.0.1:5433/ire_rls_rehearsal'
python -m pytest tests/integration/test_postgres_rls.py -q
```

The bootstrap URL is used only to create controlled rehearsal roles, reset the
disposable schemas, and grant least-privilege access. Alembic runs through the
migrator URL. Every data assertion uses the serving URL.

Remove the disposable database when finished:

```powershell
docker compose -f docker-compose.rls.yml down -v
```

## Institution-managed rehearsal

Before UCT pilot traffic, UCT should provision a new empty database named
`ire_rls_rehearsal` and temporary roles such as `uct_ire_migrator_rehearsal`
and `uct_ire_app_rehearsal`. A UCT database administrator supplies three
time-limited URLs to the approved test operator, who runs the same test once.
The result, database-role statements, migration revision, and test output
should be retained with the pilot entry evidence. The temporary database and
roles should then be removed through UCT's change process.
