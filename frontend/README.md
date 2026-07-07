# Corveon frontend

Next.js 16 (App Router) · React 19 · TypeScript (`strict`). Server state via TanStack Query,
local UI state via Zustand, streaming via a dedicated SSE hook. UI: shadcn/ui + Radix + Tailwind;
charts via Recharts; motion via Framer Motion.

## Local dev
```bash
pnpm install          # Node 20+ (24 LTS recommended)
pnpm dev              # http://localhost:3000
pnpm lint && pnpm typecheck && pnpm test
```

## Layout
```
app/          Next.js routes — (auth), (app)/chats/[chatId], (app)/dashboard,
              (app)/settings, (app)/org/trusted-sources
components/    design-system + feature components
lib/          api client, SSE hook, state stores, design tokens
tests/        Vitest (unit/component) + Playwright (e2e, a11y)
```

## Conventions
- WCAG 2.2 AA: semantic HTML, focus management, keyboard nav, ARIA, contrast-compliant tokens,
  reduced-motion support; verified with axe-core.
- Five evidence source-classes and severity levels have **distinct, tokenized colors** (§14).
- The API base URL and SSE base URL come from `NEXT_PUBLIC_*` env vars. **SSE connects to the
  FastAPI backend, never a Vercel serverless function** (§23.3 / ADR-0007).
- Share types with the backend via generated OpenAPI types (contract tests keep them honest).
