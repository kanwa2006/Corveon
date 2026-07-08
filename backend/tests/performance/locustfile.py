"""Performance smoke (docs/DEVELOPER.md: Locust, hot-path latency/throughput).

Not wired into the pass/fail CI gate — shared runners give noisy, non-
reproducible latency numbers, and gating merges on them would trade CI
stability for a number nobody could act on. CI instead runs this headless for
a few seconds against the same live backend the schemathesis contract job
already starts, asserting only that every task completes with a 2xx/3xx/4xx
(never a 5xx) under concurrent load — a real regression class (a hot path
that only breaks under concurrency) that the sequential pytest suite can't
catch. Run locally for actual latency/throughput numbers:

    locust -f tests/performance/locustfile.py --host http://localhost:8000
"""

from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class ChatUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        email = f"locust-{uuid.uuid4()}@example.com"
        password = "correcthorsebattery"
        credentials = {"email": email, "password": password}
        self.client.post("/api/v1/auth/register", json=credentials, name="/auth/register")
        response = self.client.post("/api/v1/auth/login", json=credentials, name="/auth/login")
        token = response.json()["access"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(3)
    def list_chats(self) -> None:
        self.client.get("/api/v1/chats", name="/chats [list]")

    @task(2)
    def create_and_read_chat(self) -> None:
        response = self.client.post(
            "/api/v1/chats", json={"title": "Locust chat"}, name="/chats [create]"
        )
        if response.status_code == 201:
            chat_id = response.json()["id"]
            self.client.get(f"/api/v1/chats/{chat_id}/messages", name="/chats/{id}/messages [list]")

    @task(1)
    def me(self) -> None:
        self.client.get("/api/v1/auth/me", name="/auth/me")
