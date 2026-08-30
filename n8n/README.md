# AIPP · n8n Workflow Suite

**20** production-shaped n8n workflows that turn AIPP into a full AI-Ops
platform for SRE / Platform Engineering. Every workflow is 100 % **n8n
Community-Edition compatible**:

- No `Code` nodes — only visual/no-code building blocks
- No dependency on the Variables API (Community CE doesn't ship it)
- All secrets held by **AIPP** — n8n only carries a shared bearer to
  `POST /api/proxy/*` on the AIPP host (Secret-Vault Proxy contract)
- HITL approvals via **native Slack Block Kit interactive buttons**
  bridged back to n8n through AIPP's HMAC-verified
  `/api/slack/interactions` endpoint

```
n8n/
├── build_workflows.py          # Python generator — regenerate anytime
├── workflows/*.json            # 20 import-ready n8n JSONs (gitignored)

├── scripts/
│   ├── deploy.sh               # push + activate via n8n REST API
│   ├── smoke_test_all.sh       # deploy + fire + validate all 17
│   ├── demo_reset.sh           # one-command defense-demo reset
│   ├── hitl_demo.sh            # end-to-end HITL smoke test
│   ├── dedupe_workflows.py     # remove ghost / duplicate workflows
│   └── push_variables.sh       # only for n8n editions with Variables API
└── README.md                   # this file
```

---

## 🚀 Quick start on your AIPP application server

```bash
cd ~/MSPROJECT/AIPP-AI-Driven-Pipeline-Platform-RACE/n8n

# 1) Regenerate all 17 JSONs
python3 build_workflows.py
ls workflows/*.json      # should list 17 files

# 2) Dry-run to see what will change on the n8n server
bash scripts/deploy.sh --dry-run

# 3) Push to your n8n instance (reads ../.env for N8N_BASE_URL + N8N_API_KEY)
bash scripts/deploy.sh

# 4) Push AND flip every workflow to Active in one shot
bash scripts/deploy.sh --activate-all

# 5) Push just one workflow
bash scripts/deploy.sh --file 07_k8s_troubleshoot_assistant.json
```

Reruns are idempotent — existing workflows get **PUT** (updated), new
ones get **POST** (created). Credential bindings are NOT lost on update.

---

## 🧪 Smoke-test all 17 workflows

```bash
bash scripts/smoke_test_all.sh                # full run
bash scripts/smoke_test_all.sh --local-only   # skip Azure-dependent flows
bash scripts/smoke_test_all.sh --skip-deploy  # already deployed
bash scripts/smoke_test_all.sh --skip-build   # skip build_workflows.py
```

The script:
1. Rebuilds every workflow JSON (`python3 build_workflows.py`)
2. Pushes + activates every JSON via the n8n REST API
3. Fires each workflow with the correct trigger:
   - `webhook`   → `POST /webhook/<path>` (JSON body)
   - `form`      → `POST /form/<path>` (multipart)
   - `schedule`  → marked as "verify in n8n UI" (CE has no run-now API)
   - `error`     → skipped (only fires on other-flow crashes)
4. Waits 12 s for HITL executions to park at their Wait nodes
5. Prints a colour-coded pass / fail matrix with the failing node +
   an actionable fix hint per failure
6. Snapshots `/api/proxy/health` so you can see which local
   integrations AIPP thinks are configured

Expected results after a fresh bring-up:
- **7 workflows** report `success` (K8s Troubleshoot, Grafana, Incident
  Commander, SOP, SLO Burn-Rate, Log Anomaly, Pipeline Review)
- **4 workflows** report `running` — the HITL flows are correctly
  parked at their Wait node waiting for a Slack click (01 Azure Vending,
  03 Access Review, 05 Pipeline Digest, 14 Chaos)
- **6 workflows** show `—` (schedules that haven't hit their cron yet)

---

## 🎬 Defense demo reset

```bash
bash scripts/demo_reset.sh                 # wipe past executions +
                                           # fire fresh HITL webhooks
bash scripts/demo_reset.sh --keep          # skip cleanup
bash scripts/demo_reset.sh --auto-approve  # automatically approve all
bash scripts/demo_reset.sh --auto-reject   # automatically reject all
```

Each fresh webhook uses a **random `run_id`** to avoid n8n execution
cache collisions.

---

## 🔐 Credentials to set up ONCE in the n8n UI

Before any workflow can execute, add these credentials in the n8n UI
(**Settings → Credentials → New**). Names must match exactly.

| Credential name | Type | Value |
|---|---|---|
| `slack-aipp` | Slack API (OAuth2) | Bot token starting with `xoxb-` (see Slack app setup) |
| `openai-aipp` | OpenAI API | Your OpenAI key **or** an Emergent LLM key |

Everything else lives in AIPP's `.env` and is reached via the
Secret-Vault Proxy — the n8n host itself needs **only** these
environment variables (or a `.env` file the container reads):

```bash
AIPP_BASE_URL=http://<aipp-host>:8001
AIPP_API_KEY=<same value as PROXY_API_KEY in AIPP's .env>

# Slack channel routing (all optional — defaults exist)
SLACK_CH_APPROVE=platform-approvals
SLACK_CH_DRIFT=platform-drift
SLACK_CH_PROVISION=platform-provisioning
SLACK_CH_STATUS=platform-status
SLACK_CH_K8S=platform-k8s
SLACK_CH_TROUBLESHOOT=platform-troubleshoot
SLACK_CH_ALERTS=platform-alerts
SLACK_CH_FINOPS=finops
SLACK_CH_SECURITY=security-access-review
SLACK_CH_INCIDENTS=incidents
SLACK_CH_INCIDENT_COMMS=incident-comms
SLACK_CH_RUNBOOKS=sre-runbooks
SLACK_CH_SLO=sre-slo
SLACK_CH_DR=sre-dr
SLACK_CH_CHAOS=sre-chaos
SLACK_CH_LOGS=sre-logs

# Only if Azure workflows should hit Azure directly (rather than via proxy)
AZURE_SUB=<subscription-id>
AZURE_TENANT=<tenant-id>
AZURE_CLIENT_ID=<sp-client-id>
AZURE_CLIENT_SECRET=<sp-secret>

# Only if any workflow ever short-circuits the proxy
SVCMAP={"api-*":"backend-team","web-*":"frontend-team"}
```

**Every other infra secret** (Kubernetes token, GitHub PAT, Proxmox
token, Grafana key, ADO PAT, IaC repo path) lives ONLY in AIPP's `.env`.
n8n reaches those systems by calling `/api/proxy/*` on AIPP. A
compromised n8n cannot exfiltrate infra credentials.

---

## 💬 Slack app setup (one-time, ~5 min)

1. https://api.slack.com/apps → **Create New App** → From scratch → name
   it *AIPP*
2. **OAuth & Permissions** → add scopes:
   * `chat:write` — post messages
   * `channels:read` — resolve channel names
   * `chat:write.customize` — post as AIPP identity
3. **Interactivity & Shortcuts** → toggle **on** → Request URL:
   `https://<aipp-public-url>/api/slack/interactions`
4. **Slash Commands** (optional) → add if you want native invocation:
   * `/troubleshoot` → `https://<n8n-host>/webhook/aipp-troubleshoot`
   * `/aipp-sub` → `https://<n8n-host>/webhook/aipp-sub-vending`
5. Install to workspace → copy **Bot User OAuth Token** (`xoxb-…`) →
   paste into `slack-aipp` credential in n8n
6. **Basic Information** → copy **Signing Secret** → put as
   `SLACK_SIGNING_SECRET` in AIPP `.env` → `docker compose restart backend`
7. Create the channels listed above and `/invite @aipp` in each

---

## 📋 The 17 workflows at a glance

| # | Workflow | Trigger | HITL? | AI does |
|---|---|---|---|---|
| 00 | Error Sink | errorTrigger | — | Central failure logger |
| 01 | Azure Subscription Vending | webhook | ✅ Slack | Drafts Terraform landing zone → PR |
| 02 | IaC Drift Detector | schedule (daily 03:00) | — | Narrates `terraform plan` diffs |
| 03 | Access Review Automator | schedule (quarterly) | ✅ Slack | Ranks dormant / risky users |
| 04 | Developer Self-Service Portal | form | ✅ Slack | Sizes VM + picks Proxmox / Azure |
| 05 | Pipeline Status Digest | schedule (30 min) | — | Aggregates ADO + GHA runs |
| 06 | K8s Health Scorecard | schedule (daily 07:00) | — | Scores cluster 0-100 |
| 07 | K8s Troubleshoot Assistant | webhook | — | Diagnoses pod failures |
| 08 | Grafana Observability Auto-Remediator | webhook | — | Picks safe remediation |
| 09 | Weekly Azure Cost Review | schedule (Mon 09:00) | — | Narrates WoW cost delta |
| 10 | Incident Commander Bot | webhook (Azure Monitor) | — | 5-step: accept→review→check→assign→comms |
| 11 | SOP / Runbook Generator | webhook | — | Drafts runbook from timeline + RCA |
| 12 | Azure SLO Burn-Rate Monitor | schedule (5 min) | — | Decides page / ticket / silent |
| 13 | DR Readiness Drill Scheduler | schedule (quarterly) | — | Designs safe DR drill |
| 14 | Chaos Engineering Assistant | form | ✅ Slack | Designs Chaos Mesh experiment |
| 15 | Log Anomaly Hunter | schedule (hourly) | — | Detects new-and-unusual patterns |
| 16 | Pipeline Review Gate (HITL) | webhook | ✅ Slack | Every AIPP pipeline generation |

**HITL flows** post a Slack Block Kit card with ✅ Approve / ❌ Reject
buttons + a copy-paste `curl` fallback for the resume URL.

---

## 🛠 Regenerating / customising workflows

`build_workflows.py` is the source of truth. To change a prompt, add a
Slack channel, or swap models, edit the relevant `wf_XX_*` function and
rerun:

```bash
python3 build_workflows.py       # regenerates all 17 JSONs
bash scripts/deploy.sh           # pushes updates (idempotent PUT)
```

The API deploy is idempotent — existing workflows get PUT, not
duplicated. You will NOT lose your credential bindings on update.

Guard-rails baked into the builder (60+ pytest invariants):

- No `Code` nodes anywhere
- No stub `https://example.com` URLs
- No hard-coded infra secrets (all calls go through `$vars.AIPP_BASE_URL`
  or the proxy helper)
- Every HITL Wait node has `httpMethod`, `responseCode`, `responseMode`
  set at the correct top level (fixes n8n 1.6x silent-bypass bug)
- Every upstream node of a Wait is marked `alwaysOutputData: true` +
  `continueOnFail` so the flow reaches the Wait even if a preceding
  Slack/LLM call briefly fails

---

## 🧹 Cleaning up duplicate workflows

If a deploy ran twice against a server without the idempotent PUT flag,
you may end up with ghost duplicates:

```bash
python3 scripts/dedupe_workflows.py --dry-run    # preview
python3 scripts/dedupe_workflows.py              # keep highest ID per name
```

---

## 🔄 SSH deploy (alternative to REST)

If the n8n API is not reachable from the AIPP app server but SSH is:

```bash
export N8N_SSH_HOST="vmadmin@n8n-host.local"
export N8N_SSH_KEY="$HOME/.ssh/id_rsa"
export N8N_CLI_PATH="/usr/local/bin/n8n"
bash scripts/deploy.sh --ssh
```

This scps each JSON to `/tmp` on the n8n host and runs
`n8n import:workflow --input=/tmp/<file>.json` remotely.

---

## ❓ Troubleshooting

| Symptom | Fix |
|---|---|
| `401 Unauthorized` on deploy | n8n API key expired/scoped wrong. Regenerate: n8n → Settings → API → Create API key. Update `N8N_API_KEY` in `../.env`. |
| `429 Too Many Requests` | Cloudflare rate-limit. Loop with a 2-s sleep between JSONs. |
| "Workflow could not be activated because it has no credential" | Add `slack-aipp` + `openai-aipp` in the n8n UI first, then open each workflow, click each red-highlighted node, and select the matching credential. Save. Retry activation. |
| Slack messages not appearing | Invite the AIPP bot to the channel: type `/invite @aipp`. |
| Slack card click does nothing | Interactivity Request URL not set in the Slack app manifest, or `SLACK_SIGNING_SECRET` mismatch — check `curl http://<aipp>/api/slack/health`. |
| HITL flow completes immediately without waiting | You are on a pre-2026-02 build. Rebuild + redeploy — Iter-31 fixed the Wait-node bypass. |
| Chaos form workflow #14 returns HTTP 500 | Form Trigger expects `multipart/form-data`. Latest `smoke_test_all.sh` uses `-F`; older versions used `-d` (URL-encoded). Pull the latest script. |
| Duplicate workflows accumulating in n8n | Run `python3 scripts/dedupe_workflows.py`. |
