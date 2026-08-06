# Access Control Matrix

Authentication proves who presented a token. Authorisation additionally checks
the action, tenant, domain assignment, resource ownership, separation of
duties, and resource state. Browser page visibility reduces accidents; it is
not the enforcement boundary.

| Role | Permitted work | Explicitly denied work |
| --- | --- | --- |
| Subject | Their own evidence, evaluation, trace, and review case; approved public policy information. | Other subjects' records; staff workspaces; policy, source, mapping, or casework changes. |
| Staff member | Assigned-domain evidence intake, cited fact proposals, institutional context, low-risk metadata, assistance, and decision-review casework. | Policy changes, release publication, and attestation of their own proposal or record. |
| Policy editor | No-code domain setup, policy drafts, handbook source intake, mapping submission, and ambiguity records. | Release approval, own-release publication, and other domains. |
| Approver | Independently review facts, context, mappings, calibration cases, ambiguities, and publish a different author's eligible release. | Approval or certification of their own proposal, record, calibration suite, or draft. |
| Auditor | Read-only governance, source, mapping, assistance, policy, and trace inspection in assigned domains. | Every write route. |
| Tenant administrator | Monitored break-glass administration across tenant domains; identifier-only durable-job status. | Bypassing immutable release/mapping transitions or separation-of-duties checks; automatic dead-letter replay. |

## Required checks per protected operation

1. Validate the bearer token and required claims.
2. Use the server-derived tenant, role, domain assignments, and subject ID;
   never accept them from the browser request body as authority.
3. Check the role may perform the action.
4. Check tenant and assigned domain access.
5. Check subject ownership where a personal record is involved.
6. Check resource state and separation of duties before mutation.
7. Let PostgreSQL RLS apply the final tenant boundary.

The generated workspace capability response intentionally contains only role,
role label, experience, and permitted view names. It excludes person IDs,
subject IDs, and domain assignments.
