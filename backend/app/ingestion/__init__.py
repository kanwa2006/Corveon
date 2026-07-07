"""Ingestion pipeline (§12) — parse, OCR, chunk, embed.

Format-specific parsers via an extensible registry (PDF/PyMuPDF, DOCX, PPT/PPTX,
Markdown, images/Pillow). OCR (Tesseract/OCRmyPDF) invoked only for scanned/image
inputs. Structure-aware, token-bounded chunking with overlap. Local CPU embeddings
(sentence-transformers, 384-dim) — the embedding ``model_id`` is recorded in
provenance and every similarity query filters on it (§23.4). Stages are emitted
as SSE progress events; work runs in ARQ workers with heartbeats and timeouts.
"""
