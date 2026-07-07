# ADR-0004: DDInter 2.0 + openFDA for drug–drug interactions (not RxNav DDI)

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
Drug–drug interaction (DDI) detection needs an authoritative, free, programmatic source. The **NLM
RxNav Drug–Drug Interaction API was discontinued on 2024-01-02** and must not be relied upon.

## Decision
Use **DDInter 2.0** (Xiong et al., *Nucleic Acids Research* 2025;53(D1):D1356–D1364 — 2,310 drugs,
302,516 DDI records with mechanism + management text; https://ddinter2.scbdd.com) as the **primary**
source, loaded as a **pinned local snapshot**. Use **openFDA label-derived interactions** as a
fallback. Each interaction returns a severity + source provenance. RxNav is used only for RxNorm
**normalization** (`findRxcuiByString`, `getApproximateMatch`), not for DDIs.

## Consequences
- DDI results are reproducible (pinned, checksummed snapshot in `drug_data_snapshots`) and auditable.
- No dependency on a discontinued API.
- Tradeoff: we own snapshot ingestion/versioning for DDInter and periodic refresh.

## Alternatives considered
- **RxNav DDI API:** discontinued — non-starter.
- **Commercial DDI databases:** not free/open; incompatible with the free-infra MVP goal.
