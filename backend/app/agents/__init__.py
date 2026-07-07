"""Agents — one file per single-responsibility agent.

Each agent implements the common protocol ``run(state) -> state`` over a typed
Pydantic state object and self-registers; adding an agent adds a routing branch,
never an orchestrator redesign. Catalog (§7): query-understanding, task-planning,
retrieval, evidence-verification, clinical-safety, medication-safety, document-
understanding, ocr, reasoning, citation-verification, response-generation,
response-review, risk-assessment, export-generation. Agent outputs are schema-validated.
"""
