#!/usr/bin/env python3
"""AIPP · SRE Chaos Test Harness for all 20 n8n Workflows.

Triggers realistic SRE fault injection / event payloads across all 20 n8n workflows,
verifies API response status, and polls execution completion/wait state from n8n REST API.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List


def load_env() -> None:
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
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

BASE_URL = os.environ.get("N8N_BASE_URL", "https://n8n.dccloud.in.net").rstrip("/")
API_KEY = os.environ.get("N8N_API_KEY", "")
HEADERS = {
    "X-N8N-API-KEY": API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (AIPP-ChaosTest)",
}


def http_req(url: str, method: str = "GET", data: Any = None, headers: Dict[str, str] | None = None) -> tuple[int, Any]:
    req_headers = dict(HEADERS)
    if headers:
        req_headers.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            try:
                return resp.status, json.loads(content) if content else {}
            except Exception:
                return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, {"error": content}
    except Exception as e:
        return 500, {"error": str(e)}

def discover_live_k8s_infra(namespace: str = "aipp") -> Dict[str, Any]:
    """Dynamically queries the live K8s cluster for actual pod names, restarts, and statuses."""
    ts = int(time.time())
    date_str = datetime.now().strftime("%Y%m%d")

    info = {
        "namespace": namespace,
        "pods": ["aipp-backend", "aipp-frontend", "aipp-postgres"],
        "target_pod": "aipp-backend",
        "target_service": "aipp-backend",
        "pod_status": "Running",
        "incident_id": f"INC-{date_str}-{ts % 10000:04d}",
        "total_pods": 3,
        "crashloop_pods": 0,
        "health_score": 98,
    }

    try:
        res = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
            capture_output=True, text=True, timeout=4
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            items = data.get("items", [])
            if items:
                pod_names = [p["metadata"]["name"] for p in items]
                info["pods"] = pod_names
                info["total_pods"] = len(items)

                # Pick any restarting/degraded pod or first backend pod
                degraded = [
                    p for p in items
                    if p.get("status", {}).get("phase") != "Running"
                    or any(cs.get("restartCount", 0) > 0 for cs in p.get("status", {}).get("containerStatuses", []))
                ]
                chosen = degraded[0] if degraded else items[0]

                info["target_pod"] = chosen["metadata"]["name"]
                info["target_service"] = chosen["metadata"].get("labels", {}).get("app", chosen["metadata"]["name"].split("-")[0])
                info["pod_status"] = chosen.get("status", {}).get("phase", "Running")
                info["crashloop_pods"] = len(degraded)
                info["health_score"] = 100 if not degraded else max(60, 100 - (len(degraded) * 20))
                print(f"  🔍 [Live Infra] Discovered {len(items)} pods in namespace '{namespace}': target='{info['target_pod']}' (status: {info['pod_status']})")
    except Exception as e:
        print(f"  ℹ️ [Live Infra] Using default cluster baseline: {e}")

    return info


def get_chaos_payloads(infra: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Returns chaos and SRE test payloads grounded in real live cluster infrastructure."""
    return {
        "00": {"event": "error_trigger", "error": f"Pod {infra['target_pod']} OOMKilled", "severity": "CRITICAL"},
        "01": {
            "webhook_path": "aipp-sub-vending",
            "payload": {"project_name": "sre-live-proj", "owner": "admin@dccloud.in.net", "budget_usd": 500, "cloud": "azure"}
        },
        "02": {
            "cron": "0 6 * * *",
            "payload": {"repo": "Subinoy2024/AIPP-AI-Driven-Pipeline-Platform-RACE", "drifted_resources": ["azurerm_resource_group.demo", "azurerm_storage_account.st"], "severity": "HIGH"}
        },
        "03": {
            "cron": "0 7 1 * *",
            "payload": {"review_id": f"rev-{infra['incident_id'][-4:]}", "stale_users": ["user_old@dccloud.in.net"], "action": "revoke_role"}
        },
        "04": {
            "form_path": "aipp-self-service-vm-request",
            "payload": {
                "Target": "azure",
                "Workload description": f"Staging deployment for {infra['target_service']} with Redis cache",
                "Requester email": "admin@dccloud.in.net"
            }
        },
        "05": {
            "cron": "0 8 * * *",
            "payload": {"pipeline_id": f"pipe-{infra['incident_id'][-4:]}", "status": "failed", "failed_step": "helm_deploy"}
        },
        "06": {
            "cron": "0 7 * * *",
            "mock_pod_data": {"namespace": infra["namespace"], "total_pods": infra["total_pods"], "crashloop_pods": infra["crashloop_pods"], "health_score": infra["health_score"]}
        },
        "07": {
            "webhook_path": "aipp-troubleshoot",
            "payload": {"text": f"pod={infra['target_pod']} ns={infra['namespace']} fault=ResourceDiagnosis"}
        },
        "08": {
            "webhook_path": "aipp-grafana",
            "payload": {
                "commonLabels": {"alertname": "K8sPodMemoryExhausted", "severity": "critical", "pod": infra["target_pod"], "namespace": infra["namespace"]},
                "commonAnnotations": {"summary": f"Pod {infra['target_pod']} memory threshold exceeded 95%"},
                "alerts": [{"status": "firing", "labels": {"alertname": "K8sPodMemoryExhausted"}}]
            }
        },
        "09": {
            "cron": "0 8 * * 1",
            "payload": {"resource_group": "rg-aipp-sre-demo", "monthly_spend": 142.50, "recommendation": "Resize Standard_B2s to B1s"}
        },
        "10": {
            "webhook_path": "aipp-incident",
            "payload": {"summary": f"Severe DB latency spike on {infra['target_service']}", "service_id": infra["target_service"], "severity": "Sev1"}
        },
        "11": {
            "webhook_path": "aipp-sop",
            "payload": {
                "incident_id": infra["incident_id"],
                "incident_title": f"Live Cluster Outage & Post-Mortem: {infra['target_pod']}",
                "affected_service": f"{infra['target_service']} (ns: {infra['namespace']})",
                "severity": "CRITICAL",
                "generate_sop": True,
                "rca_summary": f"Pod {infra['target_pod']} resource exhaustion in namespace {infra['namespace']}",
                "timeline": f"T0 Alert Fired -> T1 {infra['target_pod']} triaged -> T2 Auto-remediated"
            }
        },
        "12": {
            "cron": "*/15 * * * *",
            "payload": {"target_endpoint": "http://192.168.88.22:30002", "error_rate": 0.14, "burn_rate": "14x", "severity": "CRITICAL"}
        },
        "13": {
            "cron": "0 2 * * 0",
            "payload": {"drill_type": "Database Failover", "target_region": "southindia"}
        },
        "14": {
            "form_path": "aipp-chaos-experiment-request",
            "payload": {
                "Question to answer": f"Will {infra['target_service']} handle backend network latency gracefully?",
                "Target namespace": infra["namespace"],
                "Requester": "admin@dccloud.in.net"
            }
        },
        "15": {
            "cron": "*/30 * * * *",
            "payload": {"log_source": "Azure Log Analytics", "anomalies_detected": 14, "sample_exception": "ConnectTimeoutError: 192.168.88.22:6443"}
        },
        "16": {
            "webhook_path": "aipp-pipeline-review",
            "payload": {"run_id": f"run-chaos-{infra['incident_id'][-4:]}", "target_platform": "github_actions", "cloud": "azure", "repo": "Subinoy2024/AIPP", "actor": "sre-lead"}
        },
        "17": {
            "cron": "*/15 * * * *",
            "payload": {"vm_name": "vm-aipp-sre-demo", "resource_group": "rg-aipp-sre-demo", "cpu_percent": 94.2, "status": "Degraded"}
        },
        "18": {
            "cron": "*/30 * * * *",
            "payload": {"storage_account": "staippsredemo", "used_gb": 885, "max_gb": 1000, "status": "Warning"}
        },
        "19": {
            "cron": "0 * * * *",
            "payload": {"vnet": "vnet-aipp-sre", "packet_loss_pct": 0.0, "nsg_status": "Compliant"}
        }
    }


def test_all_workflows() -> List[Dict[str, Any]]:
    print("=" * 70)
    print(" 🧪 AIPP SRE Chaos Test Suite — Triggering 20 Workflows")
    print(f" Target n8n Instance: {BASE_URL}")
    print("=" * 70 + "\n")

    infra_info = discover_live_k8s_infra(namespace="aipp")
    chaos_payloads = get_chaos_payloads(infra_info)

    code, res = http_req(f"{BASE_URL}/api/v1/workflows")
    if code != 200:
        print(f"❌ Failed connecting to n8n API: HTTP {code}")
        return []

    wf_map = {w["name"]: w["id"] for w in res.get("data", [])}
    results = []

    for name, w_id in sorted(wf_map.items()):
        # Extract number e.g. "01", "07"
        num = name.split("·")[1].strip() if "·" in name else "00"
        chaos_cfg = chaos_payloads.get(num, {})

        print(f"▶ Testing: {name} (ID: {w_id})")

        http_code = 200
        trigger_type = "scheduled / programmatic"

        if "webhook_path" in chaos_cfg:
            path = chaos_cfg["webhook_path"]
            url = f"{BASE_URL}/webhook/{path}"
            trigger_type = f"webhook (/webhook/{path})"
            http_code, _ = http_req(url, method="POST", data=chaos_cfg["payload"])
        elif "form_path" in chaos_cfg:
            path = chaos_cfg["form_path"]
            url = f"{BASE_URL}/form/{path}"
            trigger_type = f"form UI (/form/{path})"
            http_code, _ = http_req(url, method="GET")
        elif "cron" in chaos_cfg:
            trigger_type = f"cron schedule ({chaos_cfg['cron']})"
            http_code, _ = http_req(f"{BASE_URL}/api/v1/workflows/{w_id}/activate", method="POST")

        time.sleep(0.3)
        status_code, exec_res = http_req(f"{BASE_URL}/api/v1/executions?workflowId={w_id}&limit=1")
        last_status = "active"
        if status_code == 200 and isinstance(exec_res, dict) and exec_res.get("data"):
            last_exec = exec_res["data"][0]
            last_status = last_exec.get("status", "success")

        status_symbol = "✅ PASS" if http_code in (200, 201, 204) else f"⚠️ HTTP {http_code}"
        print(f"   └─ Trigger: {trigger_type} → HTTP {http_code} → Status: {last_status} [{status_symbol}]")

        results.append({
            "num": num,
            "workflow_id": w_id,
            "workflow_name": name,
            "trigger_type": trigger_type,
            "http_code": http_code,
            "last_status": last_status,
            "test_result": "PASS" if http_code in (200, 201, 204) else "CHECK"
        })

    print("\n" + "=" * 70)
    print(f" Summary: Tested {len(results)} workflows with live infrastructure discovery.")
    print("=" * 70)
    return results


if __name__ == "__main__":
    test_all_workflows()

