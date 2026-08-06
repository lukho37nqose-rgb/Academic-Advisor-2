# Cacisa Systems public site

This directory is an intentionally isolated, static company site. It must not
share a runtime, cookie domain, authentication client, database, object store,
or analytics identifier with a tenant or provider application.

The public copy and visual rules are maintained in
[`docs/CACISA_BRAND_SYSTEM.md`](../docs/CACISA_BRAND_SYSTEM.md). The logo PNG is
a working identity asset, not a substitute for a future designer-produced vector
master.

## Local preview

Any static file server can serve this directory. For example:

```powershell
cd company-site
python -m http.server 8088
```

Open `http://127.0.0.1:8088`.

## Container preview

```powershell
docker build -t cacisa-public-site .
docker run --rm -p 8088:8080 cacisa-public-site
```

The image uses an unprivileged Nginx process and a restrictive CSP. It contains
no forms, tracking, authentication, or institution data.

## Production hosts

Suggested public hostnames:

| Purpose | Hostname |
| --- | --- |
| Company and research | `cacisa.systems` and `www.cacisa.systems` |
| Synthetic demonstration | `demo.cacisa.systems` |
| Status | `status.cacisa.systems` |

Keep the following separate from this public deployment:

| Purpose | Hostname pattern |
| --- | --- |
| Tenant workspace | `{tenant}.app.cacisa.systems` or institution-owned custom domain |
| Provider operations | `ops.cacisa.systems` |
| API | `api.cacisa.systems` |
| Staging | `*.staging.cacisa.systems` |

Use separate DNS records, TLS certificates, identity-provider clients, browser
origins, and cloud accounts or at least accounts/roles for public, staging, and
production workloads. Never place a student or staff sign-in form on this site.
