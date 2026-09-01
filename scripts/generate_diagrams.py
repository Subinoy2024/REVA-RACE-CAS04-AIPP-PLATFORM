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
    """Render Master System Architecture in clean Diagrams.net / Draw.io enterprise white style."""
    fig, ax = plt.subplots(figsize=(15, 19), dpi=300)
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 19)
    ax.axis('off')

    # -------------------------------------------------------------
    # Main Title
    # -------------------------------------------------------------
    ax.text(7.5, 18.3, "AIPP — Master System Architecture", 
            fontsize=18, weight='bold', color='#B22222', ha='center', va='center')
    ax.text(7.5, 17.9, "Skill-Scoped Multi-Agent CI/CD Synthesis & Autonomous SRE Platform", 
            fontsize=10, color='#555555', ha='center', va='center')

    # Helper functions
    def draw_box(x, y, w, h, title="", subtitle="", bg="#FFFFFF", border="#2B579A", 
                 title_col="#003366", text_col="#333333", radius=0.1, lw=1.5, step_num=None):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad={radius}", 
                                      facecolor=bg, edgecolor=border, linewidth=lw)
        ax.add_patch(rect)
        if step_num:
            # Draw Step Number Badge
            badge = patches.Circle((x + 0.35, y + h - 0.35), 0.22, facecolor='#B22222', edgecolor='none')
            ax.add_patch(badge)
            ax.text(x + 0.35, y + h - 0.35, str(step_num), color='white', fontsize=9, weight='bold', ha='center', va='center')
            
        if title and subtitle:
            ax.text(x + w/2 + (0.15 if step_num else 0), y + h*0.62, title, fontsize=9.5, weight='bold', color=title_col, ha='center', va='center')
            ax.text(x + w/2 + (0.15 if step_num else 0), y + h*0.28, subtitle, fontsize=7.8, color=text_col, ha='center', va='center')
        elif title:
            ax.text(x + w/2, y + h/2, title, fontsize=9.5, weight='bold', color=title_col, ha='center', va='center')

    def draw_dashed_group(x, y, w, h, title, border="#666666", bg="#F9FAFB"):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0.1", 
                                      facecolor=bg, edgecolor=border, linewidth=1.2, linestyle="--")
        ax.add_patch(rect)
        ax.text(x + 0.25, y + h - 0.3, title, fontsize=9, weight='bold', color='#444444', ha='left', va='top')

    def draw_arrow(x1, y1, x2, y2, color="#2B579A", lw=1.8, style="->"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle=style, color=color, lw=lw, mutation_scale=14))

    # -------------------------------------------------------------
    # STEP 1: Personas & Interaction (Top Left)
    # -------------------------------------------------------------
    draw_box(1.0, 15.6, 4.0, 1.6, "1. User Input & Control Tower", "Platform Engineer / SRE\n8-Tab Gradio UI (Port 3300)", 
             bg="#F0F4F8", border="#2B579A", title_col="#003366", step_num="1")

    # STEP 2: FastAPI Gateway & AIPP Security Boundaries (Top Right)
    draw_dashed_group(6.5, 14.8, 7.5, 2.7, "2. API Gateway & AIPP Security Boundaries", border="#B22222", bg="#FFF5F5")
    draw_box(6.8, 15.1, 3.2, 1.7, "Scope Interceptor", "AST Tool Restriction\nPer-Agent Skill Scope", 
             bg="#FFFFFF", border="#D9534F", title_col="#B22222", step_num="2")
    draw_box(10.4, 15.1, 3.2, 1.7, "Secret-Vault Proxy", "Zero Token Exposure\nHMAC-SHA256 Gateway", 
             bg="#FFFFFF", border="#D9534F", title_col="#B22222")

    draw_arrow(5.0, 16.4, 6.5, 16.4, color="#003366")

    # -------------------------------------------------------------
    # STEP 3: Repository Analysis & MCP Ingestion (Middle Left)
    # -------------------------------------------------------------
    draw_box(1.0, 12.8, 4.0, 1.6, "3. Zero-Clone Repo Tree", "GitHub / GitLab MCP Ingestion\nDependency Manifest AST", 
             bg="#F0FFF4", border="#2E7D32", title_col="#1B5E20", step_num="3")

    draw_arrow(8.4, 14.8, 3.0, 14.4, color="#1B5E20")

    # -------------------------------------------------------------
    # STEP 4: LangGraph 8-Agent State Machine (Center)
    # -------------------------------------------------------------
    draw_dashed_group(6.5, 10.4, 7.5, 3.9, "4. LangGraph Multi-Agent State Machine (AIPPState)", border="#5E35B1", bg="#F8F5FC")
    
    agents = [
        ("Tech Detection Agent", "Runtime / Build Classifier"),
        ("Architecture Agent", "Monolith / Microservice / Monorepo"),
        ("Pipeline Planning Agent", "DAG Stage & Gate Planner"),
        ("Environment Agent", "Dev / Staging / Prod Target Config"),
        ("Pipeline Generator Agent", "Deterministic AST Template Engine"),
        ("Pipeline Validation Agent", "4 Verification Gates + Self-Healing")
    ]
    for idx, (t, s) in enumerate(agents):
        row = idx // 2
        col = idx % 2
        draw_box(6.8 + col*3.6, 12.7 - row*1.1, 3.3, 0.95, t, s, 
                 bg="#FFFFFF", border="#7E57C2", title_col="#4527A0")

    draw_arrow(5.0, 13.6, 6.5, 13.6, color="#4527A0")

    # -------------------------------------------------------------
    # STEP 5: Dual pgvector RAG & Persistence Store (Middle)
    # -------------------------------------------------------------
    draw_dashed_group(1.0, 8.8, 4.6, 3.4, "5. PostgreSQL 15 + pgvector Memory", border="#00695C", bg="#E0F2F1")
    draw_box(1.3, 10.5, 4.0, 1.2, "pgvector Semantic Store", "1536-dim HNSW Cosine Index\nTop-3 Golden Pipeline RAG", 
             bg="#FFFFFF", border="#00897B", title_col="#004D40", step_num="5")
    draw_box(1.3, 9.1, 4.0, 1.2, "Relational Audit Ledger", "audit_logs (Immutable Trigger)\npipeline_runs & Telemetry", 
             bg="#FFFFFF", border="#00897B", title_col="#004D40")

    draw_arrow(6.5, 11.2, 5.6, 11.2, color="#004D40")

    # -------------------------------------------------------------
    # STEP 6: Policy Engine & AST Validation (Right Middle)
    # -------------------------------------------------------------
    draw_box(6.8, 8.6, 3.3, 1.3, "6. 12 OPA Rego Policies", "Zero-Root Container Check\nCIS Security Hardening", 
             bg="#FFFDE7", border="#FBC02D", title_col="#F57F17", step_num="6")
    draw_box(10.5, 8.6, 3.2, 1.3, "Self-Healing Retry", "AST Error Diagnostics\nMax 2 Healing Passes", 
             bg="#FFFDE7", border="#FBC02D", title_col="#F57F17")

    draw_arrow(10.25, 10.4, 8.45, 9.9, color="#F57F17")
    draw_arrow(8.45, 9.9, 10.5, 9.25, color="#F57F17")

    # -------------------------------------------------------------
    # STEP 7: Slack HITL Approval Gate (Bottom Left / Center)
    # -------------------------------------------------------------
    draw_box(1.0, 6.2, 4.6, 1.8, "7. Slack Block-Kit HITL Gate", "Interactive Deploy Approval Card\nHMAC-SHA256 Cryptographic Sign-Off", 
             bg="#EDE7F6", border="#512DA8", title_col="#311B92", step_num="7")

    draw_arrow(8.45, 8.6, 3.3, 8.0, color="#311B92")

    # -------------------------------------------------------------
    # STEP 8: SRE Automation Suite & Multi-Cloud Deployment
    # -------------------------------------------------------------
    draw_dashed_group(6.5, 5.0, 7.5, 3.1, "8. Autonomous AIOps & Incident Doctor", border="#E65100", bg="#FFF3E0")
    draw_box(6.8, 6.3, 3.3, 1.4, "20 n8n SRE Workflows", "Live Incident Routing\nAuto-Remediation Hooks", 
             bg="#FFFFFF", border="#FB8C00", title_col="#E65100", step_num="8")
    draw_box(10.4, 6.3, 3.3, 1.4, "PipelineDoctor Agent", "Log Line Grounding (L001-L1500)\nAuto DOCX SOP Generation", 
             bg="#FFFFFF", border="#FB8C00", title_col="#E65100")
    draw_box(6.8, 5.2, 6.9, 0.9, "pgvector RCA Long-Term Memory", "F1 = 0.898 with warm memory (49 prior incidents)", 
             bg="#FFF8E1", border="#FFA000", title_col="#FF6F00")

    draw_arrow(3.3, 6.2, 6.8, 5.8, color="#E65100")

    # -------------------------------------------------------------
    # EXTERNAL ECOSYSTEM & MCP ADAPTERS (Bottom Container)
    # -------------------------------------------------------------
    draw_dashed_group(1.0, 1.5, 13.0, 3.0, "11 Model Context Protocol (MCP) Adapters & Target Multi-Cloud Infrastructure", 
                      border="#37474F", bg="#ECEFF1")
    
    eco_items = [
        ("Source Control (VCS)", "GitHub · GitLab\nZero-Clone Trees", "#1B5E20", "#2E7D32"),
        ("Target CI/CD Engines", "GitHub Actions · GitLab CI\nAzure DevOps · Tekton · Harness", "#0D47A1", "#1565C0"),
        ("Live Multi-Cloud & K8s", "AWS EKS · Azure AKS · GCP Run\nLocal K8s (aipp node)", "#311B92", "#4527A0"),
        ("Foundation AI Models", "OpenAI gpt-4o-mini\nClaude 3.5 Sonnet / Ollama", "#BF360C", "#D84315")
    ]
    for idx, (title, sub, bc, tc) in enumerate(eco_items):
        draw_box(1.3 + idx*3.1, 1.8, 2.9, 2.2, title, sub, bg="#FFFFFF", border=bc, title_col=tc)

    draw_arrow(3.3, 6.2, 4.2, 4.5, color="#37474F")
    draw_arrow(8.5, 5.0, 8.5, 4.5, color="#37474F")

    # -------------------------------------------------------------
    # Bottom Legend / Footer Box
    # -------------------------------------------------------------
    draw_dashed_group(1.0, 0.3, 13.0, 0.9, "Legend & Security Boundaries", border="#888888", bg="#FAFAFA")
    ax.text(1.3, 0.65, "🔴 Red Nodes: AIPP Security Boundaries (Scope Interceptor & Secret-Vault Proxy)  |  Numbered Badges (1-8): Traceable End-to-End Execution Flow", 
            fontsize=8.5, color='#333333', va='center')

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_0.png", DELIVERABLE_IMG / "architecture_slide.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ Master System Architecture (White Diagrams.net Style) rendered successfully.")

# -------------------------------------------------------------
# 2. Figure 7.2: End-to-End Pipeline Generation & Validation Flow
# -------------------------------------------------------------
def render_application_flow():
    """Render 5-stage Pipeline Generation & Validation flow in clean Modern Enterprise White style."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis('off')

    # Main Header
    ax.text(8.0, 8.3, "AIPP — End-to-End Pipeline Generation & Validation Flow", 
            fontsize=17, weight='bold', color='#111827', ha='center', va='center')
    ax.text(8.0, 7.85, "Zero-Clone Ingestion · pgvector RAG · Multi-Agent AST Synthesis · 4-Gate Verification · Validated PR Emission", 
            fontsize=9.5, color='#4B5563', ha='center', va='center')

    # Stages definition
    stages = [
        ("Stage 1", "Repository Ingestion\n(Zero-Clone)", 
         "• GitHub / GitLab MCP\n• In-Memory AST Trees\n• Dependency Manifests:\n  pom.xml, package.json\n  Dockerfiles, Chart.yaml", "#1E40AF", "#EFF6FF"),
        ("Stage 2", "pgvector RAG\nTemplate Retrieval", 
         "• PostgreSQL 15 Instance\n• 1536-d Cosine Vector Store\n• HNSW Cosine Index\n• Fetches Top-3 Closest\n  Golden Pipeline Blueprints", "#047857", "#ECFDF5"),
        ("Stage 3", "LangGraph Multi-Agent\nSynthesis Mesh", 
         "• RepoAnalyst (Code Map)\n• TechDetector (Ecosystem)\n• Architect (Monolith/DAG)\n• Planner (Matrix Stages)\n• EnvAgent & AST Generator", "#6D28D9", "#F5F3FF"),
        ("Stage 4", "4-Gate Verification\n& Self-Healing", 
         "• Gate 1: AST Syntax Check\n• Gate 2: CI Schema Parser\n• Gate 3: 12 OPA Rego Policies\n• Gate 4: Zero-Secret Scan\n• Automatic AST Repair Loop", "#B45309", "#FFFBEB"),
        ("Stage 5", "Validated Artifact\n& Git PR Emission", 
         "• Validated Pipeline YAML:\n  GitHub, Azure, GitLab\n• 1-Click Pull Request\n• Zero Runner Execution\n• Immutable audit_logs Sync", "#1F2937", "#F3F4F6")
    ]

    card_w = 2.7
    card_h = 5.6
    y_pos = 1.6

    for idx, (s_tag, s_title, s_desc, border_c, bg_c) in enumerate(stages):
        x_pos = 0.6 + idx * 3.1
        
        # Outer Card
        rect = patches.FancyBboxPatch((x_pos, y_pos), card_w, card_h, boxstyle="round,pad=0.12", 
                                      facecolor=bg_c, edgecolor=border_c, linewidth=1.6)
        ax.add_patch(rect)
        
        # Stage Pill Badge
        pill = patches.FancyBboxPatch((x_pos + 0.35, y_pos + card_h - 0.45), card_w - 0.7, 0.42, 
                                     boxstyle="round,pad=0.08", facecolor=border_c, edgecolor='none')
        ax.add_patch(pill)
        ax.text(x_pos + card_w/2, y_pos + card_h - 0.24, s_tag, color='white', fontsize=9.5, weight='bold', ha='center', va='center')
        
        # Title
        ax.text(x_pos + card_w/2, y_pos + card_h - 0.95, s_title, fontsize=10, weight='bold', color=border_c, ha='center', va='center')
        
        # Inner Details Box
        inner_box = patches.FancyBboxPatch((x_pos + 0.15, y_pos + 0.2), card_w - 0.3, card_h - 1.8, 
                                          boxstyle="round,pad=0.08", facecolor='#FFFFFF', edgecolor='#E5E7EB', linewidth=1.2)
        ax.add_patch(inner_box)
        ax.text(x_pos + 0.28, y_pos + card_h - 1.85, s_desc, fontsize=8.2, color='#374151', ha='left', va='top', linespacing=1.35)

        # Connector Arrows between stages
        if idx < 4:
            ax.annotate("", xy=(x_pos + card_w + 0.38, y_pos + card_h/2), xytext=(x_pos + card_w + 0.02, y_pos + card_h/2),
                        arrowprops=dict(arrowstyle="->", color="#4B5563", lw=2.2, mutation_scale=16))

    # Self-Healing Feedback Loop Curve on Stage 4
    ax.annotate("Self-Healing AST Loop", xy=(9.9 + 1.35, y_pos + card_h + 0.1), xytext=(9.9 + 1.35, y_pos + card_h + 0.6),
                ha='center', fontsize=8.2, weight='bold', color='#B45309')

    # Footer Standard Note
    ax.text(8.0, 0.75, "Generation-Only Scope: Synthesizes and strictly verifies multi-cloud pipeline definitions without executing deployment runners.", 
            fontsize=9.2, color='#1F2937', ha='center', va='center', weight='bold')

    plt.tight_layout()
    for dest_path in [DELIVERABLE_IMG / "figure_7_1_flow.png", DELIVERABLE_IMG / "figure_7_2_pipeline_generation.png"]:
        fig.savefig(dest_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✓ Figure 7.2 (Pipeline Generation Only Flow) rendered successfully.")

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
