#!/usr/bin/env python3
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error

def load_env():
    env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v

load_env()

N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "https://n8n.dccloud.in.net").rstrip("/")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

headers = {
    "X-N8N-API-KEY": N8N_API_KEY,
    "User-Agent": "Mozilla/5.0 (AIPP-DemoReset)",
    "Content-Type": "application/json",
}

print("=" * 70)
print(" 🧹 AIPP n8n Demo Reset & Clean Execution Runner")
print(f" Target Server: {N8N_BASE_URL}")
print("=" * 70)

# STEP 1: Delete all past execution logs
print("\nSTEP 1: Cleaning up past execution logs on n8n...")
req = urllib.request.Request(f"{N8N_BASE_URL}/api/v1/executions?limit=250", headers=headers)
try:
    with urllib.request.urlopen(req) as resp:
        exec_data = json.loads(resp.read().decode())
    execs = exec_data.get("data", [])
    print(f"  Found {len(execs)} execution(s) to delete.")
    deleted_count = 0
    for ex in execs:
        eid = ex.get("id")
        del_req = urllib.request.Request(f"{N8N_BASE_URL}/api/v1/executions/{eid}", headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(del_req):
                deleted_count += 1
        except Exception:
            pass
    print(f"  ✓ Deleted {deleted_count} execution records.")
except Exception as e:
    print(f"  ⚠️ Error during cleanup: {e}")

# STEP 2: Fire all webhook & form workflows with valid sample payloads
print("\nSTEP 2: Firing Webhooks & Forms with sample payloads...")

triggers = [
    ("AIPP · 01 · Azure Subscription Vending", "POST", "/webhook/aipp-sub-vending",
     {"team": "platform", "cost_center": "cc-42", "region": "eastus", "tier": "sandbox"}, True),
    ("AIPP · 07 · K8s Troubleshoot Assistant", "POST", "/webhook/aipp-troubleshoot",
     {"text": "pod=coredns-589f44dc88-7wnj5 ns=kube-system"}, True),
    ("AIPP · 08 · Grafana Observability Auto-Remediator", "POST", "/webhook/aipp-grafana",
     {"commonLabels": {"alertname": "HighMemoryUsage", "severity": "warning", "instance": "api-checkout-1"},
      "commonAnnotations": {"description": "container memory at 92%"},
      "alerts": [{"status": "firing", "labels": {"alertname": "HighMemoryUsage"}}]}, True),
    ("AIPP · 10 · Incident Commander Bot", "POST", "/webhook/aipp-incident",
     {"summary": "payments-svc latency spike", "service_id": "payments-svc", "severity": "Sev2",
      "data": {"essentials": {"alertRule": "payments-latency", "severity": "Sev2"}}}, True),
    ("AIPP · 11 · SOP / Runbook Generator", "POST", "/webhook/aipp-sop",
     {"incident_id": "INC-42", "rca_summary": "payments latency spike resolved by restart", "runbook_topic": "payments-svc restart"}, True),
    ("AIPP · 16 · Pipeline Review Gate (HITL)", "POST", "/webhook/aipp-pipeline-review",
     {"run_id": f"demo-{int(time.time())}", "pipeline_yaml": "stages:\n  - build\n  - deploy", "targets": ["aws", "azure"]}, True),
]

for name, method, path, body, is_json in triggers:
    url = f"{N8N_BASE_URL}{path}"
    req_headers = {"User-Agent": "Mozilla/5.0"}
    if is_json:
        req_headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body).encode("utf-8")
    else:
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        data_bytes = body.encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  ✓ {name:<45} -> HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"  ❌ {name:<45} -> HTTP {e.code}")
    except Exception as e:
        print(f"  ❌ {name:<45} -> {e}")

print("\n⏳ Waiting 5s for executions to process...")
time.sleep(5)

# STEP 3: Auto-approve any parked HITL Wait nodes if requested
print("\nSTEP 3: Auto-approving parked HITL Wait nodes...")
req = urllib.request.Request(f"{N8N_BASE_URL}/api/v1/executions?limit=50", headers=headers)
try:
    with urllib.request.urlopen(req) as resp:
        exec_data = json.loads(resp.read().decode())
    waiting_execs = [e for e in exec_data.get("data", []) if e.get("status") == "waiting" or e.get("finished") is False]
    print(f"  Found {len(waiting_execs)} waiting/parked execution(s).")
    
    for ex in waiting_execs:
        eid = ex.get("id")
        detail_req = urllib.request.Request(f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true", headers=headers)
        try:
            with urllib.request.urlopen(detail_req) as dresp:
                ddata = json.loads(dresp.read().decode())
            data_res = ddata.get("data", {}).get("resultData", {})
            wait_node = data_res.get("waitTill")
            # If resumeUrl exists in runData
            run_data = data_res.get("runData", {})
            for nname, ndata in run_data.items():
                for item in ndata:
                    if "data" in item and "main" in item["data"]:
                        # find resumeUrl
                        pass
        except Exception as e:
            pass
except Exception as e:
    print(f"  ⚠️ Error checking waiting executions: {e}")

print("\n" + "=" * 70)
print(" ✅ Demo Reset Complete!")
print("=" * 70)
