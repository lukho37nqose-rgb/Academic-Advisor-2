# Key Management

Each newly released policy stores a canonical signed payload, SHA-256 digest,
RSA-PSS signature, signing-key identifier, and public-key snapshot. The public
snapshot permits historical verification after a key is rotated.

## Required operating rules

1. Store `GOVERNANCE_PRIVATE_KEY` only in an institution-approved secrets
   manager or signing service. It must never appear in source control, logs,
   browser code, test fixtures, or database exports.
2. Set a meaningful `GOVERNANCE_KEY_ID` for every active key.
3. Keep retired public-key snapshots and release bundles. Retiring a private
   key must not make historic releases unverifiable.
4. Rotate keys through a controlled release: provision new key, verify existing
   historic bundles, publish a separately approved release, record the owner,
   and retain revocation evidence.
5. Treat a failed signature verification as a security event. In production,
   evaluation rejects an incomplete or invalid verification bundle.

Current limitation: a release signs policy and release scheduling metadata and
the evaluator re-compiles the signed policy to compare it with the persisted
graph. It does not yet include a policy-source manifest hash. That link is an
open control, not an implied property of the present signature.
