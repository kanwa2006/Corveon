# Corveon — Security & Threat Model

Corveon handles clinical text and must fail safe. This documents the security model (§11) and how
to report issues. Security is defense-in-depth; no single control is trusted alone.

## Reporting a vulnerability
Do **not** open a public issue for security reports. Email the maintainer (see repository profile)
with details and reproduction steps. We aim to acknowledge within a few business days. Please give
us reasonable time to remediate before any public disclosure.

## Authentication & authorization
- OAuth2 password flow with JWT: short-lived **access** + longer-lived **refresh** tokens.
- Passwords hashed with **Argon2id**. Secrets (JWT signing key, provider keys) come from env only.
- **RBAC** roles: `user`, `org-admin`, `superadmin`. Every endpoint authorizes on **both** user
  identity **and** resource ownership.

## Tenancy & per-chat isolation (the core invariant)
Enforced three ways (§10.2):
1. **Application guard** — every content query passes the active `chat_id`.
2. **Postgres Row-Level Security** — policies keyed on `chat_id` / `user_id`.
3. **Repository invariant** — the repository refuses any content query lacking a `chat_id` predicate.
There is **no cross-chat or global-memory read path**. Cross-chat use requires an explicit user
import that copies/links artifacts into the target chat.

## Prompt-injection defenses
- Untrusted document text is **data, not instructions** — passed as clearly delimited data under a
  system-prompt contract.
- An input screen strips/escapes instruction-like patterns.
- Tool/agent invocation is **orchestrator-gated**, never triggered by document content.
- Agent/model outputs are validated against expected schemas before use.

## Malicious-upload defenses
MIME + magic-byte validation · size caps · extension allowlist · per-file sandboxed parsing ·
image/PDF-bomb limits · no execution of uploaded content · antivirus scan hook. Failed validation
never reaches the pipeline.

## Encryption & least privilege
- TLS in transit everywhere. At rest: provider disk encryption + application-level encryption for
  sensitive fields.
- DB roles scoped; workers hold only needed capabilities; object-store access via **short-lived
  signed URLs** only.

## Privacy
- Minimize sensitive-data collection; store only what is necessary; support data deletion.
- **Right to erasure (§23.6):** hard delete cascades across `messages`, `documents`,
  `document_chunks`, `chunk_embeddings`, `images`, `medications`, `medication_findings`,
  `saved_responses`, and the corresponding R2 objects, run as an ARQ job, with a single audit-log
  entry recording the *action* (not the content). Archive is soft/reversible; delete is irreversible.
- **Data-residency policy:** route org-trusted / sensitive text to local Ollama by policy
  (`SENSITIVE_TEXT_PROVIDER`) because some free-tier provider inputs may be used for training.

## Auditability
Append-only `audit_log` for auth events, uploads, exports, admin actions, and evidence/medication
findings — capturing actor, action, entity, IP, and metadata (never sensitive content).

## Safety posture (clinical)
Corveon is **not a medical device** and never replaces a licensed professional. It never fabricates
facts, dosages, or citations; the medication rules engine is the source of truth; the platform
never answers confidently on suspected misinformation and always surfaces uncertainty, provenance,
and a recommendation to consult a professional.

## Dependency & code scanning
`pip-audit` (Python deps) and `bandit` (Python SAST) run in CI; frontend deps are audited via the
package manager. Findings gate the pipeline.
