## What & why
<!-- One reviewable concern. Link the issue. What changed and why. -->

## Per-feature order followed
Architecture → Database → API → Backend → Frontend → Testing → Docs (tick what applied):
- [ ] Architecture / design (ADR added if a decision was resolved)
- [ ] Database (migration + RLS for any new content table; models↔migrations in sync)
- [ ] API (contract + docs/API.md updated)
- [ ] Backend
- [ ] Frontend
- [ ] Testing
- [ ] Documentation

## Definition of Done
- [ ] All relevant test layers green in CI (see docs/DEVELOPER.md matrix)
- [ ] Medication logic changes include **golden tests** against a pinned snapshot (if applicable)
- [ ] `ruff` + `mypy --strict` + `bandit` + `pip-audit` (backend) / `lint` + `typecheck` + `build` (frontend) pass
- [ ] New code paths add an OTel span + `trace_id` log
- [ ] Every content query is `chat_id`-scoped (per-chat isolation intact)
- [ ] No hardcoded provider in business logic; no always-on RAG
- [ ] No secrets committed; uploads validated; document text treated as data
- [ ] Docs updated in this PR

## Safety check
- [ ] No fabricated medical facts/dosages/citations; rules engine remains the source of truth
- [ ] No confident answers on suspected misinformation
