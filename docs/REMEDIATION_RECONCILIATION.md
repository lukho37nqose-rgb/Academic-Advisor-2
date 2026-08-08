# Remediation Reconciliation Ledger

This ledger records what commit `2dfa28c` actually contains compared with what
its commit message claimed. It is forensic documentation only. It does not
restore files, make architectural recommendations, or verify that any finding
was fully remediated.

## Evidence Used

- Baseline commit inspected: `2dfa28ca24dfc895cde696196521290f563a24e3`
- Commit subject: `feat: apply forensic audit remediation (F-001 through F-019)`
- Source of claimed contents: `git show -s --format=fuller 2dfa28c`
- Source of changed paths: `git show --name-status 2dfa28c`
- Source of resulting tree contents: `git ls-tree -r --name-only 2dfa28c`

The commit changes 182 paths relative to its parent.

## Commit-Message Claims Versus Git Evidence

| Commit-message claim or later disputed artifact | Git evidence in `2dfa28c` | Status |
| --- | --- | --- |
| Main F-001 through F-019 remediation work | Commit changes application code, migrations, tests, frontend files, deployment docs, and assurance docs across 182 paths. This ledger does not verify each finding semantically. | Present as broad code/documentation changes; finding-by-finding verification not established here. |
| Harden Docker context: explicit COPY set, non-root UID 10001:10001, STOPSIGNAL | `Dockerfile` and `.dockerignore` exist in the resulting tree, but neither is changed by `2dfa28c`. | Not established as a change made by `2dfa28c`. |
| Fix two Alembic heads: merge revision + 14 new control migrations | `2dfa28c` adds 13 Alembic files under `alembic/versions/`. | Partially supported by path evidence; exact "14" and merge-head claim not verified here. |
| Add provider control plane OIDC separation | Commit adds/changes provider-related app, database, auth, docs, and frontend files, including `alembic/versions/f4a1b7d83e25_add_provider_control_plane.py`, `app/services/auth.py`, `app/services/ui_capabilities.py`, `frontend/src/ProviderApp.tsx`, and `frontend/src/authConfig.ts`. | Present as committed implementation artifacts; operational readiness not verified here. |
| Add `deploy/terraform` | Directory exists in the resulting tree and is changed by `2dfa28c`. | Present in commit. |
| Add `deploy/static-surfaces` | No path under `deploy/static-surfaces/` exists in the resulting tree or changed-path list. | Not present in commit. |
| Add `company-site` | Directory exists in the resulting tree and is changed by `2dfa28c`. | Present in commit. |
| Add `pilot/uct_humanities` | Directory exists in the resulting tree and is changed by `2dfa28c`. | Present in commit. |
| Add CI workflow `deployment-readiness` | `.github/workflows/deployment-readiness.yml` exists in the resulting tree and is changed by `2dfa28c`. | Present in commit. |
| Add CI workflow `publish-image` | `.github/workflows/publish-image.yml` is absent from the resulting tree and changed-path list. | Not present in commit. |
| Add CI workflow `deploy-environment` | `.github/workflows/deploy-environment.yml` is absent from the resulting tree and changed-path list. | Not present in commit. |
| Add `.gitattributes` for LF normalisation | `.gitattributes` is absent from the resulting tree and changed-path list. | Not present in commit. |
| Expand `.dockerignore` and `.gitignore` boundaries | `.gitignore` is changed by `2dfa28c`; `.dockerignore` exists in the resulting tree but is not changed by `2dfa28c`. | Partially present. |
| Add `REMEDIATION_STATUS.md` tracking all findings | `docs/REMEDIATION_STATUS.md` is absent from the resulting tree and changed-path list. | Not present in commit. |

## Later Patch-Only Artifacts Not Present In `2dfa28c`

These files or directories were observed during recovery as rejected-patch or
untracked debris. Git does not show them in the `2dfa28c` tree or changed-path
list.

| Path | Status in `2dfa28c` |
| --- | --- |
| `tools/aws_oidc_credentials.sh` | Not present. |
| `tools/run_real_stack_e2e.sh` | Not present. |
| `app/services/audit_context.py` | Not present. |
| `app/services/connectors.py` | Not present. |
| `app/services/pdf_sandbox.py` | Not present. |
| `app/services/pdf_sandbox_worker.py` | Not present. |
| `frontend/provider.html` | Not present. |
| `frontend/src/ConfigurationFailure.tsx` | Not present. |
| `frontend/src/provider-main.tsx` | Not present. |
| `frontend/src/runtimeConfig.ts` | Not present. |
| `frontend/tests/real-stack.spec.ts` | Not present. |
| `frontend/vite.provider.config.ts` | Not present. |
| `frontend/vite.tenant.config.ts` | Not present. |
| `status-site/` | Not present. |
| `tests/release_factory.py` | Not present. |
| `tests/test_evidence_disposition.py` | Not present. |
| `tests/test_forensic_remediation_controls.py` | Not present. |
| `deploy/terraform/monitoring.tf` | Not present. |

## Boundary

This ledger establishes only repository contents. It should not be used as
evidence that deployment, PostgreSQL RLS, provider OIDC, static-surface hosting,
PDF sandboxing, connector integration, or real-stack E2E behavior has been
exercised.
