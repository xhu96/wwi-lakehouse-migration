# ADR 0005: No personal data in gold

**Status:** accepted · **Date:** 2026-10

## Context

The legacy reports were run by anyone with database access, so names, emails and phone numbers of customers and cleaners were visible to every report user. Under GDPR, access to personal data should be limited to people who need it, and erasure requests must be honoured everywhere.

## Decision

- Personal data (names, emails, phones) stays in `silver`, which is restricted to data engineers.
- Gold carries only what analysis needs: email domain, segment, zone, signup date. Cleaners appear with a display name (first name and initial) because operations reviews them by name.
- Erased customers keep their history for revenue and retention, with no identifiers.

## Consequences

- Gold can be granted to all analysts and to Power BI service principals without masking rules.
- Use cases that need contact details (marketing exports) read silver through a dedicated, audited path, out of scope for this repository.
- The next step is to express these grants, plus column masks on silver, as code (see the roadmap).
