# Pinned drug-data snapshot loaders

Deterministic medication safety (§9) requires **reproducible, auditable** reference data. Loaders in
this directory import each source as a **pinned, checksummed snapshot** recorded in the
`drug_data_snapshots` table (`source, version, checksum, imported_at`). Golden tests pin against a
specific snapshot version so rule outputs are stable across time (ADR-0004, ADR-0005).

## Sources (verified July 2026)
| Source | Version pin | Use | License / access |
|---|---|---|---|
| **DDInter 2.0** | dataset release | primary drug–drug interactions | free; https://ddinter2.scbdd.com (Xiong et al., *NAR* 2025;53(D1):D1356–D1364) |
| **openFDA labels** | snapshot date | DDI fallback + label text | free API; 240/min, 120k/day with key |
| **Beers Criteria 2023 (AGS)** | 2023 update | potentially-inappropriate-prescribing | encoded as versioned rule set (*JAGS* 2023;71(7):2052–2081) |
| **STOPP/START v3** | v3 (2023) | deprescribing (133 STOPP + 57 START = 190) | encoded rule set (*Eur Geriatr Med* 2023;14(4):625–632) |
| **RxNorm / RxNav** | monthly release | normalization to RxCUI | free; ≤20 req/s; **no DDI API** (discontinued 2024-01-02) |

## Rules
- **Never commit raw snapshots** — they are fetched, not vendored (`data/snapshots/` is gitignored).
  Loaders record only the version + checksum in the database.
- Each import verifies the checksum before use; a mismatch fails loudly.
- Development/CI use **Synthea** synthetic patients (no PHI). MIMIC-IV (PhysioNet Credentialed
  Health Data License v1.5.0) is reserved for advanced evaluation only and is never shipped.

## Dev/test data
- **Synthea** — default synthetic patients for development and CI; no credentialing required.
- **MIMIC-IV** — research-only, credentialed; used for advanced evaluation, not in the product.

Loader implementations are added in the Month 6–12 phase (see [../../docs/ROADMAP.md](../../docs/ROADMAP.md)).
