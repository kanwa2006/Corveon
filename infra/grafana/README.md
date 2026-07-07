# Grafana dashboards

Grafana dashboard JSON for Corveon's Prometheus metrics (§16) lives here. Planned dashboards:

- **API** — request latency (histogram), error rate, in-flight requests.
- **Providers** — per-provider success/latency/quota, circuit-breaker state, failover events.
- **Pipeline** — ARQ queue depth, job durations by stage, retry/heartbeat health.
- **Retrieval** — embedding/search timings, cache hit rate.

Dashboards are added alongside the observability stack (Roadmap: Month 1). Metric names are defined
where each metric is emitted; keep dashboard panels in sync with those names.
