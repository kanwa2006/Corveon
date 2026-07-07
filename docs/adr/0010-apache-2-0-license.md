# ADR-0010: Apache-2.0 license

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
Corveon is an open-source flagship that may also become the basis of a startup. The blueprint fixes
"open-source" but did not name a license — a documentation gap resolved here.

## Decision
License the project under **Apache-2.0**.

## Consequences
- Permissive (encourages adoption/contribution) **and** includes an explicit patent grant and
  patent-retaliation clause — valuable for a healthcare product with future commercial ambitions.
- Requires preserving NOTICE/attribution on redistribution; contributions are inbound-Apache-2.0
  (stated in CONTRIBUTING.md).
- Reversible in principle but relicensing is costly once contributors join, so it is fixed early.

## Alternatives considered
- **MIT:** simpler, but no patent grant — weaker protection for a healthcare/commercial path.
- **AGPL-3.0:** strong copyleft, but deters commercial adoption and complicates a SaaS/startup path.
