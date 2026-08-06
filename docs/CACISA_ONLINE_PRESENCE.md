# Cacisa Systems Online Presence

This document describes the public company, synthetic-demo, tenant, provider,
and API surfaces for Cacisa Systems. It is a product and deployment boundary,
not a claim that any customer is live.

## Brand and company structure

- **Company:** Cacisa Systems (Pty) Ltd once incorporated.
- **Core technology:** Institutional Reasoning Engine.
- **First domain:** Higher education policy and curriculum reasoning.
- **Implementation capability:** Policy formalisation, governance, integration,
  validation, and support.
- **Public-interest programme:** From Opacity to Legibility.
- **Brand descriptor:** Making institutional reasoning legible.

The company is not a generic student app and is not an institution's policy
author. An institution remains responsible for its policies, authoritative
sources, permitted exceptions, decision owners, and review routes. Cacisa is
responsible for accurately representing, executing, and tracing approved rules.

## Public host map

| Surface | Suggested host | Data and identity boundary |
| --- | --- | --- |
| Public company site | `cacisa.systems`, `www.cacisa.systems` | Static content only. No product sign-in, tenant cookies, institutional data, or behavioural tracking. |
| Synthetic demo | `demo.cacisa.systems` | Static or isolated demo environment. Synthetic policy, evidence, and people only. No connection to production systems. |
| Public operational status | `status.cacisa.systems` | Availability and incident notices only. Never disclose tenant records or internal security detail. |
| Tenant application | `{tenant}.app.cacisa.systems` initially | Institution-specific OIDC client, CSP, tenant boundary, and data. The preferred long-term route is an institution-owned custom domain such as `reasoning.institution.ac.za`. |
| Provider operations | `ops.cacisa.systems` | Cacisa-only OIDC client and provider roles. No tenant token is accepted here. |
| Product API | `api.cacisa.systems` | API audience validates tenant and provider issuers separately. Not a browser-facing information site. |
| Staging | `*.staging.cacisa.systems` | Separate infrastructure and secrets. No production evidence or personal data. |

Use distinct browser origins, TLS certificates, OIDC clients, secrets, and
cloud roles for each row. A single code repository does not mean a single trust
boundary.

## Current code mapping

| Concern | Existing component |
| --- | --- |
| Tenant workspace | `frontend/src/App.tsx` built with `VITE_APP_SURFACE=tenant` |
| Provider-only workspace | `frontend/src/ProviderApp.tsx` built with `VITE_APP_SURFACE=provider` |
| Capability routing | `app/services/ui_capabilities.py` and `GET /api/v1/session/capabilities` |
| Tenant/domain/subject enforcement | API access controls and PostgreSQL RLS migrations |
| Policy lifecycle | Draft, independent approval, signed release, effective-date applicability, immutable audit artefacts |
| Evidence and handbook safety | Hash-verified source handling, bounded PDF/OCR review, accepted-fact workflow |
| Public company site | `company-site/`, a separate static deployment |

## Public-site rules

The company site may explain Cacisa's method and show only synthetic or
explicitly approved material. It must not:

- use a tenant API token or call a tenant API;
- contain an institutional login form;
- claim a live customer, integration, compliance certification, security
  certification, or outcome result that has not been established;
- mention a prospective university as a customer or pilot without written
  approval;
- collect transcript, policy, evidence, appeal, or support information;
- install session replay or advertising pixels in any tenant workspace.

Public contact is deliberately email-only until Cacisa has an approved,
privacy-reviewed CRM and a clear lawful basis for collecting enquiries.

## Synthetic demonstration rules

The demonstration helps an institution understand the product before it shares
data. It must use made-up policy names, values, people, release identifiers,
and evidence references. It must prominently state that it is non-operative.

The demo may show:

- an approved policy release;
- a cited evidence position;
- a confirmed, provisional, or review-required explanation;
- a policy trace and human review route.

The demo may not imitate a named institution's unpublished policy or suggest
that it evaluates a real student's standing.

## Content architecture

The public site should organise content around a person's real questions:

1. What does Cacisa make possible?
2. What does it refuse to decide?
3. How does an institution keep authority?
4. What would implementation ask of our people and systems?
5. How are privacy, accessibility, uncertainty, and review handled?
6. What can a prospective partner see without sharing data?

The `From Opacity to Legibility` programme belongs to the public company site.
It can host research writing, talks, implementation principles, and future
ethics-approved work. It is not a second legal entity or a source of customer
data.

## Deployment sequence after legal and domain setup

1. Register the domain and create DNS records for the public site, demo, and
   status page. Enable HTTPS and HSTS at the edge.
2. Deploy `company-site/` to a dedicated static-hosting account/project. Do
   not attach it to the API VPC or tenant database.
3. Create `ops`, `api`, `staging`, and tenant DNS entries only when their own
   identity, TLS, hosting, logging, and incident contacts are approved.
4. Configure institutional tenant applications only after an institution has
   supplied the OIDC contract, approved the tenant scope, and named data and
   policy authorities.
5. Before using any real data, complete the deployment gates already listed in
   `docs/RELEASE_READINESS.md`, `docs/PILOT_DEPLOYMENT_RUNBOOK.md`, and
   `docs/assurance/`.

## Brand application

Use the Cacisa Graphite frame with Teal for the reasoning path, Green for
confirmed information, Amber for provisional information, Coral for a review
or conflict, and Paper/Cloud as readable surfaces. Status must always include
a written label and familiar icon or shape; colour is never the only signal.

The selected Canva mark is an exploratory identity direction. Before commercial
launch, a designer should produce approved vector masters and usage files
(SVG/PDF/EPS or AI), confirm font licences, and run print and contrast checks.
