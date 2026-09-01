"""Generate publication-quality architecture and flow diagrams for AIPP Final Capstone Deliverable."""

import os
import shutil
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Directories
PROJECT_ROOT = Path("/Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM")
DELIVERABLE_IMG = PROJECT_ROOT / "final_deliverable" / "images"
PAPER_IMG = PROJECT_ROOT / "Project_Paper" / "images"
DOCS_DIR = PROJECT_ROOT / "docs"

DELIVERABLE_IMG.mkdir(parents=True, exist_ok=True)
PAPER_IMG.mkdir(parents=True, exist_ok=True)

# Copy all existing images from Project_Paper/images and docs into final_deliverable/images
for src_dir in [PAPER_IMG, DOCS_DIR]:
    if src_dir.exists():
        for item in src_dir.glob("*.png"):
            dest = DELIVERABLE_IMG / item.name
            shutil.copy2(item, dest)

print(f"Copied existing images to {DELIVERABLE_IMG}")

# Style settings
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['font.family'] = 'sans-serif'

# -------------------------------------------------------------
# 1. Figure 7.1: Master System Architecture
# -------------------------------------------------------------
def render_master_architecture():
    fig, ax = plt.subplots(figsize=(15, 9.5), dpi=300)
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 9.5)
    ax.axis('off')

    # Title Banner
    ax.text(7.5, 9.1, "AIPP — AUTOMATED PIPELINE PLATFORM: MASTER SYSTEM ARCHITECTURE", 
            fontsize=15, weight='bold', color='#58a6ff', ha='center', va='center')
    ax.text(7.5, 8.75, "Skill-Scoped Multi-Agent Orchestration · Dual pgvector RAG · Zero-Trust Gateway · 20 n8n AIOps Workflows", 
            fontsize=9.5, color='#8b949e', ha='center', va='center')

    def draw_box(x, y, w, h, title, subtitle="", bg="#161b22", border="#30363d", text_col="#c9d1d9", radius=0.15, title_col=None):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad={radius}", 
                                      facecolor=bg, edgecolor=border, linewidth=1.5)
        ax.add_patch(rect)
        if title:
            tc = title_col or text_col
            if subtitle:
                ax.text(x + w/2, y + h*0.62, title, fontsize=9.5, weight='bold', color=tc, ha='center', va='center')
                ax.text(x + w/2, y + h*0.28, subtitle, fontsize=7.5, color='#8b949e', ha='center', va='center')
            else:
                ax.text(x + w/2, y + h/2, title, fontsize=9, weight='bold', color=tc, ha='center', va='center')

    # Layer 1: Personas & Interaction
    draw_box(0.5, 6.9, 3.2, 1.4, "PERSONAS & INTERFACES", "Platform Eng / SRE / Compliance", bg="#1f242c", border="#388bfd", title_col="#58a6ff")
    draw_box(0.7, 7.0, 1.3, 0.55, "Slack Block-Kit", "HITL Sign-offs", bg="#161b22", border="#7ee787", title_col="#7ee787")
    draw_box(2.2, 7.0, 1.3, 0.55, "Control Tower", "8-Tab Gradio UI", bg="#161b22", border="#7ee787", title_col="#7ee787")

    # Layer 2: API Gateway & Security Interceptors (Red Boundary)
    draw_box(4.2, 6.9, 4.2, 1.4, "API GATEWAY & SECURITY", "FastAPI (Async I/O · RBAC)", bg="#1f242c", border="#f85149", title_col="#f85149")
    draw_box(4.4, 7.0, 1.8, 0.55, "Scope Interceptor", "AST Tool Restriction", bg="#2b1a1f", border="#f85149", title_col="#ff7b72")
    draw_box(6.4, 7.0, 1.8, 0.55, "Secret-Vault Proxy", "HMAC / Redaction", bg="#2b1a1f", border="#f85149", title_col="#ff7b72")

    # Layer 3: LangGraph Agent Mesh
    draw_box(8.9, 6.9, 5.6, 1.4, "LANGGRAPH MULTI-AGENT MESH", "8 Specialised Agents (Bounded StateGraph)", bg="#1f242c", border="#a371f7", title_col="#d2a8ff")
    agents = [("Planner", "RepoAnalyst"), ("Architect", "TechAgent"), ("Generator", "Validator"), ("Deployer", "RCA Doctor")]
    for idx, (a1, a2) in enumerate(agents):
        draw_box(9.1 + idx*1.32, 7.0, 1.22, 0.55, f"{a1}\n& {a2}", "", bg="#161b22", border="#8957e5", title_col="#d2a8ff")

    # Layer 4: Dual pgvector RAG & Persistence (Middle Layer)
    draw_box(0.5, 4.3, 6.8, 2.1, "PERSISTENCE & RETRIEVAL LAYER", "PostgreSQL 15 + pgvector (1536-dim HNSW Indexing)", bg="#161b22", border="#1f6feb", title_col="#58a6ff")
    draw_box(0.8, 4.5, 2.8, 1.2, "pgvector Similarity Stores", "• Pipeline Templates (cosine)\n• RCA Incident Memory", bg="#0d1117", border="#238636", text_col="#7ee787")
    draw_box(3.9, 4.5, 3.1, 1.2, "Relational & Audit Data", "• pipeline_runs (State/Cost)\n• audit_logs (Append-Only Trigger)", bg="#0d1117", border="#388bfd", text_col="#79c0ff")

    # Layer 5: Policy Engine & n8n AIOps Engine
    draw_box(7.7, 4.3, 6.8, 2.1, "INTEGRATION & AUTOMATION SUITE", "20 Production n8n Workflows · Open Policy Agent (OPA)", bg="#161b22", border="#d29922", title_col="#e3b341")
    draw_box(8.0, 4.5, 3.0, 1.2, "20 n8n AIOps Workflows", "• 00 Error Sink → 19 NetWatcher\n• Auto DOCX Post-Mortem Sync", bg="#0d1117", border="#d29922", text_col="#f2cc60")
    draw_box(11.2, 4.5, 3.0, 1.2, "12 Rego Policy Packs", "• Zero-Root / CIS Hardening\n• AST Native Syntax Validation", bg="#0d1117", border="#388bfd", text_col="#79c0ff")

    # Layer 6: MCP Adapters & External Target Systems (Bottom Layer)
    draw_box(0.5, 1.2, 14.0, 2.6, "11 MCP ADAPTERS & EXTERNAL ECOSYSTEM INTEGRATIONS", "Model Context Protocol Tool Protocol", bg="#161b22", border="#30363d", title_col="#58a6ff")
    
    mcp_items = [
        ("CI / CD Targets", "GitHub Actions\nGitLab CI · Tekton\nAzure DevOps · Harness", "#238636", "#7ee787"),
        ("Live Infrastructure", "Kubernetes (aipp)\nPods, Secrets, Ingress\nPrometheus Alerting", "#1f6feb", "#79c0ff"),
        ("Multi-Cloud MCP", "AWS Cloud · GCP\nAzure Resource Mgr\nHashiCorp Vault", "#8957e5", "#d2a8ff"),
        ("Communication & LLM", "Slack Webhook / Socket\nOpenAI GPT-4o-mini\nDeepSeek / Ollama", "#d29922", "#f2cc60"),
    ]
    for idx, (title, sub, bc, tc) in enumerate(mcp_items):
        draw_box(0.9 + idx*3.35, 1.5, 3.0, 1.8, title, sub, bg="#0d1117", border=bc, title_col=tc)

    # Connecting Arrows
    def draw_arrow(x1, y1, x2, y2, color="#58a6ff", style="->"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle=style, color=color, lw=2, mutation_scale=15))

    draw_arrow(3.7, 7.6, 4.2, 7.6, "#58a6ff")
    draw_arrow(8.4, 7.6, 8.9, 7.6, "#58a6ff")
    draw_arrow(11.5, 6.9, 11.5, 6.4, "#d2a8ff")
    draw_arrow(4.0, 6.9, 4.0, 6.4, "#58a6ff")
    draw_arrow(4.0, 4.3, 4.0, 3.8, "#58a6ff")
    draw_arrow(11.5, 4.3, 11.5, 3.8, "#d29922")

    # Legend / Key Note
    ax.text(7.5, 0.45, "🛡️ Security Boundaries: Red boxes denote AST Scope Enforcement & Zero-Secret Vault Proxy | 100% 20/20 Test Suite Passed", 
            fontsize=9, color='#7ee787', ha='center', va='center', weight='bold')

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_0.png", PAPER_IMG / "figure_7_0.png", DELIVERABLE_IMG / "architecture_slide.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ Master System Architecture rendered successfully.")

# -------------------------------------------------------------
# 2. Figure 7.1 Flow: End-to-End Application Workflow Diagram
# -------------------------------------------------------------
def render_application_flow():
    fig, ax = plt.subplots(figsize=(15, 8.5), dpi=300)
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.5)
    ax.axis('off')

    ax.text(7.5, 8.0, "AIPP — END-TO-END PIPELINE GENERATION & DEPLOYMENT FLOW", 
            fontsize=15, weight='bold', color='#58a6ff', ha='center', va='center')
    ax.text(7.5, 7.65, "From Repository Ingestion to Slack HITL Gating & Live Deployment", 
            fontsize=9.5, color='#8b949e', ha='center', va='center')

    def draw_step(x, y, w, h, step_num, title, desc, border="#388bfd", bg="#161b22"):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.12", facecolor=bg, edgecolor=border, linewidth=1.5)
        ax.add_patch(rect)
        badge = patches.Circle((x + 0.35, y + h - 0.35), 0.22, facecolor=border, edgecolor='none')
        ax.add_patch(badge)
        ax.text(x + 0.35, y + h - 0.35, str(step_num), fontsize=8.5, weight='bold', color='#ffffff', ha='center', va='center')
        ax.text(x + 0.75, y + h - 0.35, title, fontsize=9.5, weight='bold', color='#c9d1d9', ha='left', va='center')
        ax.text(x + w/2, y + h*0.35, desc, fontsize=7.5, color='#8b949e', ha='center', va='center')

    draw_step(0.6, 4.8, 3.2, 2.2, 1, "User Ingestion", "• User inputs Repo URL\n• Target CI (GH / GL / ADO)\n• Security Scopes selected\n• FastAPI generates run_id", "#388bfd")
    draw_step(4.2, 4.8, 3.2, 2.2, 2, "Repo & AST Analysis", "• Clone / analyze file tree\n• Detect lang (Python/Node/Go)\n• Identify package managers\n• Check docker / k8s manifests", "#388bfd")
    draw_step(7.8, 4.8, 3.2, 2.2, 3, "pgvector RAG Retrieval", "• Query cosine vector store\n• Fetch top-3 golden templates\n• Inject past incident mitigations\n• Assemble prompt context", "#238636")
    draw_step(11.4, 4.8, 3.0, 2.2, 4, "LangGraph Generation", "• Planner sets DAG tasks\n• Architect selects syntax\n• Generator writes YAML\n• JSON auto-repair engine", "#8957e5")

    draw_step(11.4, 1.8, 3.0, 2.2, 5, "OPA & Syntax Validation", "• 12 Rego policy checks\n• Native CI schema parser\n• Zero-secret credential scan\n• Retry loop if syntax fails", "#d29922")
    draw_step(7.8, 1.8, 3.2, 2.2, 6, "Slack HITL Sign-Off", "• Post Slack Block-Kit card\n• Display diff & risk scores\n• Engineer clicks Approve/Reject\n• HMAC-SHA256 signature check", "#f85149")
    draw_step(4.2, 1.8, 3.2, 2.2, 7, "MCP Git & K8s Push", "• MCP commits pipeline YAML\n• Push branch to remote repo\n• Apply k8s deployment if set\n• Trigger remote CI runner", "#238636")
    draw_step(0.6, 1.8, 3.2, 2.2, 8, "Audit & Doctor Sync", "• Immutable log in audit_logs\n• Cost & latency recorded\n• Embed result to pgvector\n• Real-time SSE update to UI", "#388bfd")

    def draw_arrow(x1, y1, x2, y2, color="#58a6ff"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2.2, mutation_scale=15))

    draw_arrow(3.8, 5.9, 4.2, 5.9)
    draw_arrow(7.4, 5.9, 7.8, 5.9)
    draw_arrow(11.0, 5.9, 11.4, 5.9)
    
    draw_arrow(12.9, 4.8, 12.9, 4.0)
    
    draw_arrow(11.4, 2.9, 11.0, 2.9)
    draw_arrow(7.8, 2.9, 7.4, 2.9)
    draw_arrow(4.2, 2.9, 3.8, 2.9)

    ax.text(7.5, 0.75, "✓ Fully Automated, Closed-Loop Flow with Human-in-the-Loop Safeguards & Zero-Leakage Guarantee", 
            fontsize=9.5, color='#7ee787', ha='center', va='center', weight='bold')

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_1_flow.png", PAPER_IMG / "figure_7_1_flow.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ Application Flow Diagram rendered successfully.")

# -------------------------------------------------------------
# 3. Figure 7.2: SRE Incident Triage & Self-Healing RCA Flow
# -------------------------------------------------------------
def render_sre_rca_flow():
    fig, ax = plt.subplots(figsize=(15, 8.5), dpi=300)
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.5)
    ax.axis('off')

    ax.text(7.5, 8.0, "AIPP — SRE INCIDENT TRIAGE, CHAOS RESILIENCE & RCA WORKFLOW", 
            fontsize=15, weight='bold', color='#58a6ff', ha='center', va='center')
    ax.text(7.5, 7.65, "Workflow 11 (SOP Generator) · Live K8s Discovery · pgvector Doctor · Synchronous DOCX Export", 
            fontsize=9.5, color='#8b949e', ha='center', va='center')

    def draw_node(x, y, w, h, title, sub, col="#388bfd", bg="#161b22"):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.12", facecolor=bg, edgecolor=col, linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h*0.65, title, fontsize=9.5, weight='bold', color='#c9d1d9', ha='center', va='center')
        ax.text(x + w/2, y + h*0.3, sub, fontsize=7.5, color='#8b949e', ha='center', va='center')

    draw_node(0.5, 4.5, 3.2, 2.2, "1. Live Cluster Alert", "• K8s CrashLoopBackOff\n• Prometheus OOMKilled Alert\n• Chaos script injects fault\n• Node discovery (dck8snode2)", "#f85149")
    draw_node(4.1, 4.5, 3.2, 2.2, "2. n8n Incident Router", "• Workflow 11 / Error Sink\n• Extract topic & pod names\n• Severity-Gating (P1 vs P3)\n• Route to RCA DOCX API", "#d29922")
    draw_node(7.7, 4.5, 3.2, 2.2, "3. Doctor pgvector RAG", "• Query rca_embeddings (HNSW)\n• 1536-dim cosine similarity\n• Retrieve past incident fix\n• Synthesise root cause & SOP", "#238636")
    draw_node(11.3, 4.5, 3.2, 2.2, "4. Multi-Agent RCA", "• RCAAgent builds timeline\n• ScopeInterceptor protects tools\n• Bounded LLM budget guard\n• Produces structured remediation", "#8957e5")

    draw_node(11.3, 1.5, 3.2, 2.2, "5. DOCX Generation", "• POST /api/workflows/rca/docx\n• Professional SRE styling\n• Formatted incident post-mortem\n• Written to docs/ & downloadable", "#388bfd")
    draw_node(7.7, 1.5, 3.2, 2.2, "6. Postgres Sync", "• Upsert rca_reports table\n• Embed and save to vector store\n• Write sre.rca.docx.generated\n• Append-only audit trigger", "#238636")
    draw_node(4.1, 1.5, 3.2, 2.2, "7. Slack Notification", "• Interactive incident alert\n• Direct DOCX download link\n• Runbook remediation action\n• SRE acknowledges in Slack", "#7ee787")
    draw_node(0.5, 1.5, 3.2, 2.2, "8. Closed-Loop Health", "• Pod restarts verified\n• K8s status healthy (1/1)\n• Control Tower UI updated\n• Zero manual delay", "#388bfd")

    def draw_arrow(x1, y1, x2, y2, color="#58a6ff"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2.2, mutation_scale=15))

    draw_arrow(3.7, 5.6, 4.1, 5.6)
    draw_arrow(7.3, 5.6, 7.7, 5.6)
    draw_arrow(10.9, 5.6, 11.3, 5.6)
    
    draw_arrow(12.9, 4.5, 12.9, 3.7)
    
    draw_arrow(11.3, 2.6, 10.9, 2.6)
    draw_arrow(7.7, 2.6, 7.3, 2.6)
    draw_arrow(4.1, 2.6, 3.7, 2.6)

    ax.text(7.5, 0.65, "⚡ Continuous Platform Self-Healing with Synchronous pgvector Memory & Audit Sync", 
            fontsize=9.5, color='#7ee787', ha='center', va='center', weight='bold')

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_2_sre_flow.png", PAPER_IMG / "figure_7_2_sre_flow.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ SRE Incident Flow Diagram rendered successfully.")

# -------------------------------------------------------------
# 4. Figure 7.6: Agent Run Lifecycle State Machine
# -------------------------------------------------------------
def render_state_machine():
    fig, ax = plt.subplots(figsize=(14, 8), dpi=300)
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis('off')

    ax.text(7.0, 7.5, "AIPP — AGENT RUN LIFECYCLE (FINITE-STATE MACHINE)", 
            fontsize=15, weight='bold', color='#58a6ff', ha='center', va='center')
    ax.text(7.0, 7.15, "Formal State Graph with Skill-Scope Interceptions, Budget Exhaustion, and Self-Healing Retries", 
            fontsize=9.5, color='#8b949e', ha='center', va='center')

    def draw_state(x, y, w, h, name, desc, col="#388bfd", bg="#161b22", terminal=False):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15", 
                                      facecolor=bg, edgecolor=col, linewidth=2.0 if terminal else 1.5)
        ax.add_patch(rect)
        tag = " [TERMINAL]" if terminal else ""
        ax.text(x + w/2, y + h*0.62, name + tag, fontsize=9.5, weight='bold', color=col, ha='center', va='center')
        ax.text(x + w/2, y + h*0.28, desc, fontsize=7.5, color='#8b949e', ha='center', va='center')

    draw_state(0.6, 4.5, 2.0, 1.5, "IDLE", "Awaiting Request", "#58a6ff")
    draw_state(3.2, 4.5, 2.2, 1.5, "ANALYZING", "Repo & AST Inspection", "#58a6ff")
    draw_state(5.9, 4.5, 2.2, 1.5, "PLANNING", "DAG Task Assembly", "#58a6ff")
    draw_state(8.6, 4.5, 2.2, 1.5, "GENERATING", "YAML & Script Synthesis", "#8957e5")
    draw_state(11.3, 4.5, 2.2, 1.5, "VALIDATING", "OPA & AST Verification", "#d29922")

    draw_state(11.3, 2.0, 2.2, 1.5, "AWAITING_APPROVAL", "Slack HITL Verification", "#d29922")
    draw_state(11.3, 0.1, 2.2, 1.4, "SUCCEEDED", "Committed & Deployed", "#7ee787", terminal=True)

    draw_state(0.6, 1.5, 2.4, 1.6, "SCOPE_VIOLATION", "Unauthorized Tool Call", "#f85149", terminal=True)
    draw_state(3.5, 1.5, 2.4, 1.6, "BUDGET_EXCEEDED", "Token / Cost Exhausted", "#f85149", terminal=True)
    draw_state(6.4, 1.5, 2.4, 1.6, "REJECTED", "Rejected by Engineer", "#f85149", terminal=True)

    def draw_edge(x1, y1, x2, y2, label="", color="#58a6ff", rad=0.0):
        connectionstyle = f"arc3,rad={rad}" if rad != 0 else "arc3"
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2.0, mutation_scale=14, connectionstyle=connectionstyle))
        if label:
            mx, my = (x1 + x2)/2, (y1 + y2)/2 + 0.25
            ax.text(mx, my, label, fontsize=7.5, color='#c9d1d9', ha='center', va='center',
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#0d1117", edgecolor="#30363d", lw=0.8))

    draw_edge(2.6, 5.25, 3.2, 5.25, "Start")
    draw_edge(5.4, 5.25, 5.9, 5.25, "Ast Done")
    draw_edge(8.1, 5.25, 8.6, 5.25, "Plan Ready")
    draw_edge(10.8, 5.25, 11.3, 5.25, "YAML Built")

    draw_edge(12.0, 6.0, 10.0, 6.0, "Syntax Error (Retry ≤ 2)", color="#e3b341", rad=-0.4)

    draw_edge(12.4, 4.5, 12.4, 3.5, "OPA Valid")
    draw_edge(12.4, 2.0, 12.4, 1.5, "Approved", color="#7ee787")
    draw_edge(11.3, 2.5, 8.8, 2.5, "Rejected", color="#f85149")

    draw_edge(7.0, 4.5, 2.0, 3.1, "Scope Intercept", color="#f85149")
    draw_edge(9.5, 4.5, 4.7, 3.1, "Token Limit", color="#f85149")

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_6.png", PAPER_IMG / "figure_7_6.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ State Machine Diagram rendered successfully.")

# -------------------------------------------------------------
# 5. Figure 7.7: Entity-Relationship Database Diagram
# -------------------------------------------------------------
def render_er_diagram():
    fig, ax = plt.subplots(figsize=(14, 8.5), dpi=300)
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8.5)
    ax.axis('off')

    ax.text(7.0, 8.0, "AIPP — PERSISTENCE & pgvector ENTITY-RELATIONSHIP SCHEMA", 
            fontsize=15, weight='bold', color='#58a6ff', ha='center', va='center')
    ax.text(7.0, 7.65, "PostgreSQL 15 Relational Tables · Immutable Append-Only Audit Ledger · HNSW 1536-dim Embeddings", 
            fontsize=9.5, color='#8b949e', ha='center', va='center')

    def draw_table(x, y, w, h, tbl_name, fields, col="#388bfd"):
        hdr = patches.Rectangle((x, y + h - 0.6), w, 0.6, facecolor=col, edgecolor="#30363d")
        ax.add_patch(hdr)
        ax.text(x + w/2, y + h - 0.3, tbl_name, fontsize=9.5, weight='bold', color="#ffffff", ha='center', va='center')
        
        body = patches.Rectangle((x, y), w, h - 0.6, facecolor="#161b22", edgecolor="#30363d", linewidth=1.5)
        ax.add_patch(body)
        
        for idx, (f_name, f_type, f_key) in enumerate(fields):
            fy = y + h - 0.9 - idx*0.36
            key_col = "#e3b341" if "PK" in f_key else ("#79c0ff" if "FK" in f_key else "#8b949e")
            ax.text(x + 0.2, fy, f_key, fontsize=7.5, weight='bold', color=key_col, ha='left', va='center')
            ax.text(x + 1.1, fy, f_name, fontsize=8.0, color="#c9d1d9", ha='left', va='center')
            ax.text(x + w - 0.2, fy, f_type, fontsize=7.5, color="#8b949e", ha='right', va='center')

    draw_table(0.5, 3.8, 4.0, 3.4, "pipeline_runs", [
        ("run_id", "UUID", "[PK]"),
        ("repo_url", "VARCHAR(255)", ""),
        ("target_ci", "VARCHAR(50)", ""),
        ("status", "VARCHAR(50)", ""),
        ("duration_sec", "FLOAT", ""),
        ("cost_usd", "NUMERIC(10,4)", ""),
        ("created_at", "TIMESTAMP", ""),
    ], "#1f6feb")

    draw_table(5.0, 3.8, 4.0, 3.4, "audit_logs (Immutable)", [
        ("log_id", "BIGSERIAL", "[PK]"),
        ("run_id", "UUID", "[FK]"),
        ("actor", "VARCHAR(100)", ""),
        ("action", "VARCHAR(100)", ""),
        ("payload", "JSONB", ""),
        ("signature", "VARCHAR(64)", ""),
        ("created_at", "TIMESTAMP", ""),
    ], "#da3633")

    draw_table(9.5, 3.8, 4.0, 3.4, "rca_reports", [
        ("incident_id", "VARCHAR(50)", "[PK]"),
        ("run_id", "UUID", "[FK]"),
        ("severity", "VARCHAR(20)", ""),
        ("root_cause", "TEXT", ""),
        ("mitigation", "TEXT", ""),
        ("docx_path", "VARCHAR(255)", ""),
        ("created_at", "TIMESTAMP", ""),
    ], "#8957e5")

    draw_table(2.5, 0.5, 4.2, 2.7, "pipeline_embeddings (RAG)", [
        ("template_id", "SERIAL", "[PK]"),
        ("ci_platform", "VARCHAR(50)", ""),
        ("category", "VARCHAR(50)", ""),
        ("embedding", "vector(1536)", "[HNSW]"),
        ("template_yaml", "TEXT", ""),
    ], "#238636")

    draw_table(7.5, 0.5, 4.2, 2.7, "rca_embeddings (Memory)", [
        ("memory_id", "SERIAL", "[PK]"),
        ("incident_id", "VARCHAR(50)", "[FK]"),
        ("topic", "VARCHAR(100)", ""),
        ("embedding", "vector(1536)", "[HNSW]"),
        ("resolution_sop", "TEXT", ""),
    ], "#238636")

    def draw_rel(x1, y1, x2, y2, label="1:N", color="#58a6ff"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.8, mutation_scale=12))
        ax.text((x1+x2)/2, (y1+y2)/2 + 0.15, label, fontsize=7.5, color="#58a6ff", ha='center')

    draw_rel(4.5, 5.5, 5.0, 5.5, "1 : N")
    draw_rel(4.5, 4.8, 9.5, 4.8, "1 : 0..1")
    draw_rel(9.5, 4.0, 9.5, 3.2, "1 : 1")

    ax.text(7.0, 0.15, "🔒 Append-Only Database Trigger: Disallows UPDATE / DELETE operations on audit_logs for compliance integrity", 
            fontsize=8.5, color='#7ee787', ha='center', va='center', weight='bold')

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_7.png", PAPER_IMG / "figure_7_7.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ ER Diagram rendered successfully.")

if __name__ == "__main__":
    render_master_architecture()
    render_application_flow()
    render_sre_rca_flow()
    render_state_machine()
    render_er_diagram()
    print("\n All 5 publication-quality diagrams generated in final_deliverable/images/ and Project_Paper/images/!")
