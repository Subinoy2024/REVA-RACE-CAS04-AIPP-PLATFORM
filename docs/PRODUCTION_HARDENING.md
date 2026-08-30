# AIPP · Production Hardening Appendix

> **Scope:** items that are **out of scope for the research contribution**
> but need to happen before AIPP is deployed to real users.
> **Purpose:** show a reviewer that we know exactly what production-grade
> looks like — even where we chose not to implement it inside the thesis
> timeline.

Categorised by severity: 🔴 P0 (must-fix pre-launch), 🟠 P1 (should-fix),
🟡 P2 (nice-to-have).

---

## 1 · Access & Identity

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 1.1 | Single-tenant — no user accounts, no per-user isolation | 🔴 P0 | Add JWT auth + user column on `pipeline_runs` |
| 1.2 | No RBAC — everyone can commit YAML to any repo | 🔴 P0 | Role-based ACL: viewer / operator / admin |
| 1.3 | GitHub PATs typed into the UI (not OAuth) | 🟠 P1 | Switch to GitHub App OAuth flow |
| 1.4 | CORS is `*` in development | 🟠 P1 | Whitelist domain in production `.env` |

---

## 2 · Rate limiting & abuse

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 2.1 | Rate limiter is **in-memory** (single-process only) | 🟠 P1 | Move to Redis-backed sliding window |
| 2.2 | Limits are per-IP; a NAT masks many users | 🟠 P1 | Combine with authenticated user ID |
| 2.3 | No global LLM spend cap | 🟠 P1 | Add `LLM_MONTHLY_BUDGET_USD` in `.env` + circuit-breaker |
| 2.4 | No per-tenant quotas | 🟡 P2 | Add usage plans (free / pro / enterprise) |

**Current implementation** (`backend/core/rate_limit.py`):
- `POST /api/pipelines/generate` and `/generate/stream`: **5 req / 60 s per IP**
- `POST /api/pipeline-doctor/analyze`: **10 req / 60 s per IP**

That's enough to defend the thesis demo from a stray script. Not enough
for public launch.

---

## 3 · Secret handling

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 3.1 | Secret-scan runs at commit time — after YAML is stored in DB | 🟠 P1 | Move scan to *before* DB persistence |
| 3.2 | Scanner patterns are a starter set | 🟠 P1 | Adopt `gitleaks` or `trufflehog` as second stage |
| 3.3 | No warning banner in UI when scan finds a "medium" | 🟡 P2 | Add UI hint but don't block |
| 3.4 | Postgres is not encrypted at rest in dev | 🟠 P1 | Managed Postgres with TDE in production |
| 3.5 | Audit log is append-only in code but not enforced by DB | 🟠 P1 | Postgres row-level trigger to reject `UPDATE` on `audit_logs` |

**Current implementation** (`backend/services/secret_scanner.py`):
- Regex-based scan with 11 high/medium patterns
- Runs inside `PipelineService.generate()` → annotates result
- Runs inside `POST /api/deployment/commit` → **hard-fails** on high severity

---

## 4 · Policy & compliance

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 4.1 | No OPA policy bundle bundled with AIPP | 🟠 P1 | Ship starter `.rego` files per cloud |
| 4.2 | Security validator is regex-based, not schema-based | 🟠 P1 | Adopt `checkov` or `terrascan` as third-party gate |
| 4.3 | No SBOM emitted per generated pipeline | 🟡 P2 | Add Syft/Grype step in generated pipelines |
| 4.4 | No cost estimation for generated infrastructure | 🟡 P2 | Integrate Infracost step |

---

## 5 · Observability

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 5.1 | Logs go to stdout only | 🟠 P1 | Structured JSON logs + Loki/ELK sink |
| 5.2 | No distributed tracing | 🟠 P1 | OpenTelemetry SDK in FastAPI + LangGraph nodes |
| 5.3 | No metrics endpoint | 🟠 P1 | `/metrics` (Prometheus) — request count, latency, LLM tokens |
| 5.4 | Audit log has no retention policy | 🟡 P2 | 90-day rolling partition on `audit_logs` |

**Currently in place:**
- Structured Python logger + AsyncPG-backed `audit_logs` table
- SSE-based live UI progress
- LLM usage counter (`GET /api/llm/usage`)

---

## 6 · Availability & disaster recovery

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 6.1 | Single Postgres — no HA | 🟠 P1 | Managed Postgres w/ replica + PITR |
| 6.2 | No backup of `pipeline_runs` YAML | 🟠 P1 | Nightly `pg_dump` → object storage |
| 6.3 | No canary or blue-green deploy for AIPP itself | 🟡 P2 | Deploy behind ArgoCD |
| 6.4 | Backend is single replica | 🟠 P1 | Horizontal-scale FastAPI behind a load balancer |

---

## 7 · Supply chain

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 7.1 | Dependencies pinned but not signed | 🟠 P1 | `pip install --require-hashes` |
| 7.2 | Docker base images not scanned in CI | 🟠 P1 | Trivy in the AIPP-of-AIPP pipeline |
| 7.3 | No SLSA provenance for AIPP releases | 🟡 P2 | Sigstore + Cosign |

---

## 8 · Data privacy

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 8.1 | Repo content sent to LLM (subject to their retention) | 🟠 P1 | Add opt-in "self-hosted LLM" mode |
| 8.2 | User's commit metadata (email) can appear in generated YAML comments | 🟡 P2 | Sanitize `git config user.email` from prompts |
| 8.3 | No GDPR data-export endpoint | 🟠 P1 | `GET /api/user/export` (JSON dump of user's rows) |
| 8.4 | No account deletion flow | 🟠 P1 | `DELETE /api/user` + cascade delete |

---

## 9 · Testing & release

| # | Status | Notes |
|---|--------|-------|
| Unit tests | ✅ 490+ passing | pytest, ~7 s locally |
| Integration tests | 🟡 partial | Some tests need a live server (`backend_test.py`) |
| Load test | 🔴 missing | Add `locust` scenario for `/generate/stream` |
| Chaos test | 🔴 missing | Kill Postgres mid-generation; check user-facing error |
| Security review | 🔴 missing | External pen-test before public launch |

---

## 10 · Thesis positioning

Every item above is **known, categorised, and prioritised**. The
research contribution (multi-agent CI/CD generation + evidence-grounded
RCA across 5 platforms / 3 clouds) is orthogonal to these production
concerns. Reviewers should evaluate the research on its own terms; this
appendix is here to demonstrate awareness of production reality.
