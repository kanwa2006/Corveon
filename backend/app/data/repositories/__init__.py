"""Repository layer. For content-bearing tables (chats, documents, ...) this
layer refuses any query lacking a chat_id predicate (docs/ARCHITECTURE.md §5).
Users/Organizations are identity/tenancy roots, not content — no chat_id."""
