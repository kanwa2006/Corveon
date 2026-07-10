# ADR-0018: DDInter loader lives in `backend/app/medication/`; the real dataset is never bundled

- **Status:** Accepted
- **Date:** 2026-07-10

## Context
`data/loaders/README.md` (written during the Foundation phase) says pinned drug-data snapshot
loaders live "in this directory." `data/` is a top-level directory, a sibling of `backend/`, not a
Python package inside it — importing `backend/app/*` modules from a script physically located there
would need `sys.path`/`PYTHONPATH` manipulation with no existing tooling in this monorepo to support
it, unlike every other piece of backend logic, which is a normal, directly-testable module under
`backend/app/`.

Separately: DDInter 2.0's real dataset (2,310 drugs, 302,516 interaction records, Xiong et al. 2025,
https://ddinter2.scbdd.com) is not something this environment can fetch or is licensed to vendor
into the repository. CLAUDE.md's golden rule is explicit — never fabricate medical facts — so the
loader cannot ship with invented interaction data standing in for the real thing, even as a
"placeholder," and golden tests (blueprint §7) need *some* concrete input to assert deterministic
rule outputs against.

## Decision
- The loader implementation (`load_ddinter_snapshot`, checksum verification, CSV parsing) lives at
  `backend/app/medication/ddinter_loader.py` — a normal, mypy-strict, pytest-covered backend module,
  not a script under `data/loaders/`.
- `data/loaders/` keeps its original purpose narrowed to documentation plus the *landing spot* for an
  operator-provisioned raw snapshot file — never committed (`data/snapshots/` stays gitignored, per
  that README's own pre-existing policy).
- The loader accepts any CSV matching a documented column shape (`drug_a, drug_b, severity,
  description`) and a `--checksum` the operator can pass to verify a specific reviewed download — it
  works against the real DDInter export once provisioned, but ships with none.
- Tests (both the loader's own unit tests and the DDI rules-engine golden tests) use a small,
  explicitly-labeled synthetic fixture built from real, well-established textbook drug interactions
  (e.g. warfarin + aspirin: bleeding risk) — not the full proprietary dataset, and not invented
  interactions. This mirrors the blueprint's own precedent for Synthea synthetic patients: "no PHI
  ... default for development and CI."

## Consequences
- `POST /chats/{id}/medications/analyze` is real and shippable today; DDInter-sourced findings only
  start appearing once an operator runs the loader against a real snapshot — an honest "not yet
  provisioned" gap, not a broken feature (the openFDA label fallback, ADR-0004, still does real work
  in the meantime).
- No fabricated or placeholder medical data ever ships in this repository or its test suite.
- If `data/loaders/` later needs real executable code of its own (e.g. a fetch-and-convert script for
  a source with a public bulk-download API), it can be added without touching
  `backend/app/medication/`'s import graph.

## Alternatives considered
- **Bundle a "starter" DDInter-like dataset with a handful of real interactions as the shipped
  default:** rejected — blurs the line between "real pinned snapshot" and "always-on partial data,"
  and risks looking like the full dataset is present when it isn't; an explicit provisioning step is
  more honest.
- **Put the loader script under `data/loaders/` and add `sys.path` manipulation to import
  `backend.app.*`:** rejected — fragile, untestable the same way as the rest of the codebase, and adds
  a new, unprecedented cross-directory import mechanism for a single script.
