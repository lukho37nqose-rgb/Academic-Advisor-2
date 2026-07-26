# Incident Response

The institution must own the production incident process. This minimum
procedure makes the technical boundary explicit:

1. Contain: disable affected identity assignments, public endpoint, worker, or
   integration without modifying evidence or policy history.
2. Preserve: retain request IDs, safe telemetry, release bundles, source hashes,
   and database audit records; do not copy raw evidence into tickets.
3. Assess: determine tenant/domain/subject scope, whether a release or source
   was affected, and whether human casework needs a pause.
4. Correct: use a new governed release or reviewed source path. Never silently
   overwrite a signed release, trace, or source record.
5. Communicate: use the named privacy, policy, security, and support owners.
6. Recover and learn: verify signatures, source hashes, RLS scope, and queued
   work before resuming; record root cause and control follow-up.

Pilot entry requires named contacts, severity definitions, after-hours routing,
notification obligations, and a rehearsal. This document is not a substitute
for those institutional procedures.
