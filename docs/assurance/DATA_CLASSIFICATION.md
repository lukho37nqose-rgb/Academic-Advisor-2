# Data Classification

| Class | Examples | Repository handling rule | Institution decision required |
| --- | --- | --- | --- |
| Public policy information | Approved public guide, cited rule labels | Deliberately exposed only when a domain marks a guide public. | Publication authority and accessibility review. |
| Internal governance information | Drafts, source citations, mapping configuration, audit history | Tenant/domain-scoped; no public route. | Staff assignment, records classification, retention. |
| Confidential personal information | Evidence, claims, facts, reasoning traces, assistance/review messages | Subject/tenant scoped; no-store responses; never log raw content. | Legal basis, retention period, hosting, access review. |
| Restricted security material | JWTs, credentials, signing private keys, database passwords | Environment or managed secret only; never commit, render, or log. | Secrets manager, rotation, access monitoring, incident handling. |

Object keys use tenant prefix plus content hash; they do not include a person's
name or student number. Public policy endpoints are separate from authenticated
evidence and trace endpoints. Synthetic fixtures are not representative data
and must not be mixed with institutional records.
