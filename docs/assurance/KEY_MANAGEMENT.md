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

Current implementation: a release signs policy, release scheduling metadata,
workflow intents, and a canonical policy-source manifest hash. The evaluator
re-compiles the signed policy and compares it with the persisted graph before
production evaluation. The signature proves that the release was approved with
that citation structure; the institution must still prove that the cited
documents are authoritative and current.
