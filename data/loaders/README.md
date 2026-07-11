# Pinned drug-data snapshot loaders

Deterministic medication safety (§9) requires **reproducible, auditable** reference data. Each
source is imported as a **pinned, checksummed snapshot** recorded in the `drug_data_snapshots`
table (`source, version, checksum, row_count, created_at`). Golden tests pin against a specific
snapshot version so rule outputs are stable across time (ADR-0004, ADR-0005).

Loader **implementations** live in `backend/app/medication/` (importable/testable like every other
backend module, e.g. `app/medication/ddinter_loader.py`), not in this directory — this directory is
where an operator places the downloaded raw snapshot file before running the loader against it (see
"Rules" below; the file itself is never committed).

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

## Running a loader
```
DATABASE_URL=... python -m app.medication.ddinter_loader path/to/snapshot.csv --version 2025-01
```
Expects a UTF-8 CSV with columns `drug_a,drug_b,severity,description` (`severity` one of DDInter's
own `major`/`moderate`/`minor` scale). Pass `--checksum <sha256>` to verify against a previously
reviewed checksum; a mismatch aborts the import rather than silently ingesting a different file.

```
DATABASE_URL=... python -m app.medication.pip_loader path/to/beers2023.csv \
    --source-label beers2023 --version 2023
DATABASE_URL=... python -m app.medication.pip_loader path/to/stopp_start_v3.csv \
    --source-label stopp_start_v3 --version 3
```
Expects a UTF-8 CSV with columns `source,criterion_id,drug_names,condition_keywords,direction,
rationale,recommendation,severity` (`source` one of `beers_2023`/`stopp_v3`/`start_v3`; `drug_names`
and `condition_keywords` are `|`-pipe-separated within their cell, an empty `condition_keywords`
cell meaning the criterion is unconditional; `direction` one of `avoid`/`start_consider`). Same
`--checksum` guard as the DDInter loader.

RxNorm's monthly release loader is a later Medication-Safety Engine phase (see
[../../docs/ROADMAP.md](../../docs/ROADMAP.md)) — not yet implemented; normalization currently goes
through the live RxNav API (`app/medication/rxnorm_client.py`), not a pinned snapshot.
