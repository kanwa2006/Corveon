"""ARQ workers (§12) — async task runtime on Redis.

Job types: ingest, ocr, embed, verify, export, delete (hard-delete cascade,
§23.6). Bounded concurrency, batched embeddings, heartbeats + timeouts so no
pipeline silently stalls; failed stages retry with backoff and surface a retry
action. Independent documents process concurrently.
"""
