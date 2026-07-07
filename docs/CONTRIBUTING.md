# Contributing to Corveon

Thanks for helping build a safety-first, evidence-grounded clinical platform. Read
[`../CLAUDE.md`](../CLAUDE.md) and [DEVELOPER.md](DEVELOPER.md) first — they define how we work.
By participating you agree to the [Code of Conduct](../CODE_OF_CONDUCT.md).

## Ground rules
- **Safety over cleverness.** Never fabricate medical facts, dosages, guidelines, or citations.
- **Determinism where it matters.** The medication rules engine is the source of truth; the LLM
  only parses input and explains rule outputs.
- **Isolation is absolute.** No cross-chat reads. No global memory.
- **No hardcoded providers** in business logic. **No always-on RAG.**

## Workflow
1. Open (or claim) an issue describing the change.
2. Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`, `test/…`.
3. Follow the per-feature order: **Architecture → Database → API → Backend → Frontend → Testing → Docs.**
4. Keep PRs to one reviewable concern. Update the relevant docs in the **same PR**.
5. If you resolved a design decision, add an ADR (see [adr/](adr/) and the template).

## Commits
Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `ci:`.
Example: `feat(medication): add STOPP/START v3 screen with golden tests`.

## Definition of Done (a PR is mergeable only when)
- [ ] All relevant test layers pass in CI (see DEVELOPER.md matrix).
- [ ] Medication logic changes include **golden tests** against a pinned snapshot.
- [ ] `ruff`, `mypy --strict`, `bandit`, `pip-audit` (backend) and `lint`/`typecheck`/`build` (frontend) pass.
- [ ] New code paths add an OTel span + `trace_id` log.
- [ ] Every content query is `chat_id`-scoped; new content tables ship with an RLS policy + migration.
- [ ] Docs updated; an ADR added if a decision was resolved; a note added to the `Unreleased`
      section of [../CHANGELOG.md](../CHANGELOG.md).
- [ ] No secrets committed; uploads validated; document text treated as data.

## Local pre-push gate
```bash
cd backend && ruff check . && mypy app && pytest && bandit -q -r app && pip-audit
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

## Code review
At least one approving review; CI green; no unresolved isolation/security/determinism concerns.
Reviewers should specifically check the four ground rules above.

## Reporting security issues
See [SECURITY.md](SECURITY.md) — do not use public issues for vulnerabilities.

## License
By contributing you agree your contributions are licensed under [Apache-2.0](../LICENSE).
