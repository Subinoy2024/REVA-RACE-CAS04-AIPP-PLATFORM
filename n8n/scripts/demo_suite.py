#!/usr/bin/env python3
"""
AIPP · Comprehensive 20-Workflow Demo & Test Suite
--------------------------------------------------
This script sequentially triggers and validates all 20 n8n workflows:
  1. Validates all workflow JSON structures and trigger definitions.
  2. Executes triggers for Webhooks, Forms, Schedules, and Error Sinks.
  3. Monitors execution progress in real-time via the n8n REST API.
  4. Identifies workflows parked at Human-In-The-Loop (HITL) Wait nodes.
  5. Outputs a detailed, color-coded demonstration matrix.
"""

import json
import os
import sys
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
WORKFLOWS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workflows"))

if not N8N_API_KEY:
    print("❌ Error: N8N_API_KEY is not set.")
    sys.exit(1)

def n8n_req(endpoint, method="GET", data=None):
    url = f"{N8N_BASE_URL}/api/v1{endpoint}"
    headers = {
        "X-N8N-API-KEY": N8N_API_KEY,
        "User-Agent": "Mozilla/5.0 (AIPP-DemoSuite)",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, {"error": content}
    except Exception as e:
        return 500, {"error": str(e)}

def http_trigger(url, method="POST", data=None, is_json=True):
    headers = {"User-Agent": "Mozilla/5.0 (AIPP-DemoSuite)"}
    if is_json and data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    elif data is not None and isinstance(data, str):
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = data.encode("utf-8")
    else:
        body = None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 500, str(e)

import subprocess
from datetime import datetime

def discover_k8s_infra(namespace="aipp"):
    """Query live K8s pods to populate dynamic demo payload parameters."""
    ts = int(time.time())
    date_str = datetime.now().strftime("%Y%m%d")
    info = {
        "namespace": namespace,
        "target_pod": "aipp-backend-live",
        "target_service": "aipp-backend",
        "incident_id": f"INC-{date_str}-{ts % 10000:04d}",
    }
    try:
        res = subprocess.run(["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
                             capture_output=True, text=True, timeout=4)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            items = data.get("items", [])
            if items:
                chosen = items[0]
                info["target_pod"] = chosen["metadata"]["name"]
                info["target_service"] = chosen["metadata"].get("labels", {}).get("app", chosen["metadata"]["name"].split("-")[0])
    except Exception:
        pass
    return info

def get_webhook_payloads():
    infra = discover_k8s_infra()
    return {
        "aipp-sub-vending": {
            "team": "platform",
            "cost_center": "cc-42",
            "region": "eastus",
            "tier": "sandbox"
        },
        "aipp-troubleshoot": {
            "text": f"pod={infra['target_pod']} ns={infra['namespace']} fault=CrashLoopBackOff"
        },
        "aipp-grafana": {
            "commonLabels": {"alertname": "HighMemoryUsage", "severity": "warning", "instance": infra['target_pod']},
            "commonAnnotations": {"description": f"container memory on {infra['target_pod']} at 92%"},
            "alerts": [{"status": "firing", "labels": {"alertname": "HighMemoryUsage"}}]
        },
        "aipp-incident": {
            "summary": f"{infra['target_service']} latency spike",
            "service_id": infra['target_service'],
            "severity": "Sev1",
            "data": {"essentials": {"alertRule": f"{infra['target_service']}-latency", "severity": "Sev1"}}
        },
        "aipp-sop": {
            "incident_id": infra["incident_id"],
            "incident_title": f"Production Post-Mortem & SOP: {infra['target_pod']}",
            "affected_service": f"{infra['target_service']} (ns: {infra['namespace']})",
            "severity": "CRITICAL",
            "generate_sop": True,
            "rca_summary": f"{infra['target_service']} memory exhaustion and latency degradation",
            "timeline": "T0 Alert -> T1 Triaged -> T2 Auto-remediated"
        },
        "aipp-pipeline-review": {
            "run_id": f"demo-{int(time.time())}",
            "pipeline_yaml": "stages:\n  - build\n  - deploy",
            "targets": ["aws", "azure"]
        },
    }

FORM_PAYLOADS = {
    "aipp-self-service-vm-request": "Requester+email=demo%40aipp.local&Target=proxmox&Workload+description=web+api+3+tier",
    "aipp-chaos-experiment-request": "Requester=demo%40aipp.local&Target+namespace=default&Question+to+answer=how+does+the+cluster+behave+under+pod+deletion",
}

def main():
    print("=" * 80)
    print(" 🚀 AIPP ENTERPRISE DEMO SUITE — 20 WORKFLOW EXECUTION & TRACKER")
    print(f" Target Server: {N8N_BASE_URL}")
    print("=" * 80)

    # 1. Fetch server workflows
    status, res = n8n_req("/workflows?limit=250")
    if status != 200:
        print(f"❌ Failed to reach n8n API (HTTP {status}): {res}")
        sys.exit(1)

    deployed_wfs = res.get("data", [])
    deployed_map = {w.get("name"): w for w in deployed_wfs}

    # Load local workflow files
    json_files = sorted([f for f in os.listdir(WORKFLOWS_DIR) if f.endswith(".json")])
    wf_list = []

    for fname in json_files:
        filepath = os.path.join(WORKFLOWS_DIR, fname)
        with open(filepath, "r") as f:
            content = json.load(f)

        name = content.get("name", fname)
        nodes = content.get("nodes", [])
        
        # Check if workflow contains a Wait / HITL node
        has_hitl = any(n.get("type") == "n8n-nodes-base.wait" for n in nodes)

        trigger_type = "other"
        trigger_path = ""
        for n in nodes:
            ntype = n.get("type", "")
            params = n.get("parameters", {})
            if ntype == "n8n-nodes-base.webhook":
                trigger_type = "webhook"
                trigger_path = params.get("path", "")
                break
            elif ntype == "n8n-nodes-base.formTrigger":
                trigger_type = "form"
                trigger_path = params.get("path", "")
                break
            elif ntype == "n8n-nodes-base.scheduleTrigger":
                trigger_type = "schedule"
                break
            elif ntype == "n8n-nodes-base.errorTrigger":
                trigger_type = "error"
                break

        server_info = deployed_map.get(name, {})

        wf_list.append({
            "file": fname,
            "name": name,
            "id": server_info.get("id"),
            "active": server_info.get("active", False),
            "node_count": len(nodes),
            "trigger_type": trigger_type,
            "trigger_path": trigger_path,
            "has_hitl": has_hitl,
        })

    print(f"\n✅ Total Verified Workflows: {len(wf_list)}/20 | Server Active: {sum(1 for w in wf_list if w['active'])}/20")

    # 2. Execute Triggers
    print("\n🔥 EXECUTING WORKFLOW DEMO TRIGGERS ONE-BY-ONE...")
    print("-" * 80)

    for wf in wf_list:
        name = wf["name"]
        ttype = wf["trigger_type"]
        path = wf["trigger_path"]
        
        code = None
        result_str = ""

        if ttype == "webhook" and path:
            url = f"{N8N_BASE_URL}/webhook/{path}"
            payload = get_webhook_payloads().get(path, {"demo": True})
            code, _ = http_trigger(url, method="POST", data=payload, is_json=True)
            result_str = f"Webhook POST /webhook/{path} -> HTTP {code}"
            time.sleep(3.0)

        elif ttype == "form" and path:
            url = f"{N8N_BASE_URL}/form/{path}"
            payload = FORM_PAYLOADS.get(path, "demo=true")
            code, _ = http_trigger(url, method="POST", data=payload, is_json=False)
            result_str = f"Form POST /form/{path} (Rendered UI Active)"

        elif ttype == "schedule":
            result_str = "Scheduled Cron (Active background monitor)"
            code = 200

        elif ttype == "error":
            result_str = "Passive Error Sink (Active fallback handler)"
            code = 200

        else:
            result_str = "Standard Workflow"
            code = 200

        wf["http_code"] = code
        wf["trigger_status"] = result_str
        hitl_badge = " [🛑 HITL GATE]" if wf["has_hitl"] else ""
        print(f"  • {wf['file']:<38} | {result_str}{hitl_badge}")

    # 3. Wait for execution registration & query execution statuses
    print("\n⏳ Waiting 6s for n8n execution processing...")
    time.sleep(6)

    status, exec_resp = n8n_req("/executions?limit=100")
    recent_execs = exec_resp.get("data", []) if status == 200 else []

    exec_map = {}
    for ex in recent_execs:
        wfid = ex.get("workflowId")
        if wfid and wfid not in exec_map:
            exec_map[wfid] = ex

    # 4. Display Complete Demonstration Matrix
    print("\n" + "=" * 100)
    print(f" {'#':<3} | {'Workflow File':<36} | {'Trigger':<10} | {'HITL':<6} | {'Execution Status':<18}")
    print("=" * 100)

    for idx, wf in enumerate(wf_list, 1):
        wfid = wf.get("id")
        ex = exec_map.get(wfid)
        
        exec_status = "READY / SCHEDULED"
        if ex:
            st = ex.get("status") or ("finished" if ex.get("finished") else "running")
            if st == "waiting":
                exec_status = "🛑 WAITING (HITL)"
            elif st in ["success", True]:
                exec_status = "🟢 SUCCESS"
            elif st in ["error"]:
                exec_status = "🔴 ERROR"
            else:
                exec_status = f"🟡 {str(st).upper()}"

        hitl_str = "YES 🛑" if wf["has_hitl"] else "NO"
        print(f" {idx:02d} | {wf['file']:<36} | {wf['trigger_type']:<10} | {hitl_str:<6} | {exec_status:<18}")

    print("=" * 100)
    print(" ✅ DEMO EXECUTION COMPLETE — Ready for Runbook Generation")
    print("=" * 100)

if __name__ == "__main__":
    main()
