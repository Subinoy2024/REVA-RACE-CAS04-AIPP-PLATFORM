# AIPP — Local & Dual-Domain Kubernetes Deployment Guide

This directory contains production-ready Kubernetes manifests to deploy **AIPP (Automated Pipeline Platform)** supporting **Local Domain (`dccloud.com`)** and **Public Domain (`dccloud.in.net`)** via Cloudflare.

---

## 🏗 Cluster Architecture

* **Namespace**: `aipp`
* **PostgreSQL (pgvector)**: StatefulSet using `pgvector/pgvector:pg15` with 2GB PVC (`aipp-postgres:5432`)
* **Backend**: FastAPI Deployment (Port 8001, exposed via **NodePort 30801** & `api-aipp.dccloud.com` / `api-aipp.dccloud.in.net`)
* **Frontend**: Gradio UI Deployment (Port 3000, exposed via **NodePort 30002** & `aipp.dccloud.com` / `aipp.dccloud.in.net`)
* **Cloudflare Tunnel (`cloudflared`)**: In-cluster zero-trust tunnel daemon for secure public access via `dccloud.in.net`

---

## 🌐 Domain Configuration

| Hostname | Type | Purpose | Targeted Service |
|----------|------|---------|------------------|
| `aipp.dccloud.com` | Local Ingress | Internal UI Control Tower | `aipp-frontend:3000` |
| `api-aipp.dccloud.com` | Local Ingress | Internal API & Swagger Docs | `aipp-backend:8001` |
| `aipp.dccloud.in.net` | Public Ingress / Tunnel | External UI Access | `aipp-frontend:3000` |
| `api-aipp.dccloud.in.net` | Public Ingress / Tunnel | Public Webhooks & Slack HITL (`/api/slack/interactions`) | `aipp-backend:8001` |

---

## 🚀 Quick Deployment Steps

### 1. Build Container Images locally

From the project root directory:

```bash
# Build & tag Backend and Frontend with semantic version (e.g. v0.39.0)
docker build -t dccloudops/aipp-backend:v0.39.0 -f Dockerfile .
docker build -t dccloudops/aipp-frontend:v0.39.0 -f Dockerfile .
```

---

### 2. Configure Cloudflare Tunnel Token & API Keys (Optional)

1. Obtain your Cloudflare Tunnel token from the Cloudflare Zero Trust Dashboard (`Networks` -> `Tunnels`).
2. Add your token to `k8s/secret.yaml`:

```yaml
stringData:
  CLOUDFLARE_TUNNEL_TOKEN: "eyJh..."
  AIPP_LLM_KEY: "your-universal-llm-key"
```

---

### 3. Deploy to Kubernetes

Deploy all resources using Kustomize:

```bash
kubectl apply -k k8s/
```

---

### 4. Cloudflare Post-Configuration Checklist

1. **DNS CNAME Records**:
   - `aipp.dccloud.in.net` -> CNAME to `<YOUR-TUNNEL-ID>.cfargotunnel.com`
   - `api-aipp.dccloud.in.net` -> CNAME to `<YOUR-TUNNEL-ID>.cfargotunnel.com`
2. **SSL/TLS Encryption Mode**: Set to **Full** or **Full (Strict)**.
3. **Slack HITL Callback URL**: Set interactive webhook URL in Slack App settings to: `https://api-aipp.dccloud.in.net/api/slack/interactions`.

---

## 🌐 Accessing the Application

* **Local Domain UI**: [`http://aipp.dccloud.com`](http://aipp.dccloud.com) (or [`http://localhost:30002`](http://localhost:30002))
* **Public Domain UI**: [`https://aipp.dccloud.in.net`](https://aipp.dccloud.in.net)
* **Backend API Docs**: [`https://api-aipp.dccloud.in.net/docs`](https://api-aipp.dccloud.in.net/docs)
