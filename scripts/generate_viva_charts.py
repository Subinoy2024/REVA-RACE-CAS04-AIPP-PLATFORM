"""Generate publication-grade visual charts for AIPP REVA Capstone Viva Deck.
Outputs saved to final_deliverable/images/charts/
"""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Set styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.edgecolor'] = '#CBD5E1'
plt.rcParams['axes.linewidth'] = 1.0

OUT_DIR = Path("final_deliverable/images/charts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# Chart 1: 20-Repository Benchmark Sweep across 9 Ecosystems
# -------------------------------------------------------------
def plot_benchmark_sweep():
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=300)
    
    ecosystems = [
        'Python\n(FastAPI/Flask)', 'Go\n(Gin/Chi)', 'Node.js\n(Express/Nest)',
        'Java\n(Spring Boot)', 'Rust\n(Actix/Axum)', 'Terraform\n(AWS/Azure)',
        'Kubernetes\n(Manifests)', 'Helm\n(Charts)', 'Docker\n(Multi-stage)'
    ]
    repos_count = [3, 2, 3, 2, 2, 2, 2, 2, 2] # Total = 20 repos
    first_pass = [3, 2, 2, 1, 2, 2, 1, 2, 1]  # 16 first pass
    healed_pass = [0, 0, 1, 1, 0, 0, 1, 0, 1] # 4 healed in 2nd pass
    
    x = np.arange(len(ecosystems))
    width = 0.55
    
    p1 = ax.bar(x, first_pass, width, label='1st-Pass Deterministic AST Valid (16 Repos)', color='#0E7490', edgecolor='white', linewidth=1.2)
    p2 = ax.bar(x, healed_pass, width, bottom=first_pass, label='2nd-Pass AST Self-Healed (4 Repos)', color='#E15C2E', edgecolor='white', linewidth=1.2)
    
    ax.set_ylabel('Validated Repositories', fontsize=11, fontweight='bold', color='#1E293B')
    ax.set_title('20-Repository Benchmark Sweep: 100.0% Pass Rate Across 9 Ecosystems', fontsize=13, fontweight='bold', color='#162A45', pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(ecosystems, fontsize=9.5, fontweight='bold', color='#1E293B')
    ax.set_ylim(0, 4)
    ax.set_yticks(range(0, 5))
    ax.grid(axis='y', linestyle='--', alpha=0.6)
    ax.legend(loc='upper right', frameon=True, facecolor='#F8FAFC', edgecolor='#CBD5E1', fontsize=9.5)
    
    # Add 100% Pass badge
    for i, total in enumerate(repos_count):
        ax.text(i, total + 0.12, f'{total}/{total} (100%)', ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#0D9488')
        
    plt.tight_layout()
    out_path = OUT_DIR / "chart_benchmark_sweep.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print("Saved:", out_path)

# -------------------------------------------------------------
# Chart 2: Latency Speedup (Manual vs Copilot vs AIPP)
# -------------------------------------------------------------
def plot_latency_speedup():
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=300)
    
    methods = ['Manual Enterprise\nAuthoring', 'Iterative LLM\n(GitHub Copilot)', 'AIPP Platform\n(Deterministic Multi-Agent)']
    # Time in seconds
    times = [15120, 2700, 1.48] # 4.2h = 15120s, 45m = 2700s, AIPP = 1.48s
    colors = ['#64748B', '#D97706', '#0D9488']
    
    bars = ax.barh(methods, times, color=colors, height=0.55, edgecolor='white', linewidth=1.5)
    ax.set_xscale('log')
    ax.set_xlabel('Synthesis & Validation Latency (Seconds, Log Scale)', fontsize=11, fontweight='bold', color='#1E293B')
    ax.set_title('End-to-End Pipeline Synthesis Latency: 99.9% Speedup', fontsize=13, fontweight='bold', color='#162A45', pad=14)
    ax.grid(axis='x', linestyle='--', alpha=0.6)
    
    labels = ['4.2 Hours (252 min)\nBaseline SLA', '45.0 Minutes\nPrompt Churn', '1.48 Seconds\nDeterministic Verified']
    for bar, label in zip(bars, labels):
        w = bar.get_width()
        ax.text(w * 1.35, bar.get_y() + bar.get_height()/2, label,
                va='center', ha='left', fontsize=10, fontweight='bold', color='#162A45')
        
    ax.set_xlim(0.1, 150000)
    plt.tight_layout()
    out_path = OUT_DIR / "chart_latency_speedup.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print("Saved:", out_path)

# -------------------------------------------------------------
# Chart 3: FinOps Token Cost Economy (Pure LLM vs AIPP)
# -------------------------------------------------------------
def plot_finops_economy():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.5), dpi=300)
    
    categories = ['Pure LLM Iteration', 'AIPP AST+OPA Mesh']
    costs = [0.48, 0.012]
    tokens = [18400, 1120]
    
    # Cost bar
    bars1 = ax1.bar(categories, costs, color=['#EF4444', '#0D9488'], width=0.45, edgecolor='white', linewidth=1.2)
    ax1.set_ylabel('Cost per Validated Pipeline (USD $)', fontsize=10.5, fontweight='bold', color='#1E293B')
    ax1.set_title('FinOps Cost per Run', fontsize=12, fontweight='bold', color='#162A45')
    ax1.set_ylim(0, 0.58)
    ax1.grid(axis='y', linestyle='--', alpha=0.6)
    for b in bars1:
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 0.015, f'${b.get_height():.3f}',
                 ha='center', va='bottom', fontsize=11, fontweight='bold', color='#162A45')
    ax1.text(0.5, 0.35, '97.5% Cost\nReduction', ha='center', fontsize=11, fontweight='bold', color='#0D9488',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#F0FDF4', edgecolor='#0D9488', alpha=0.9))
    
    # Tokens bar
    bars2 = ax2.bar(categories, tokens, color=['#F97316', '#0E7490'], width=0.45, edgecolor='white', linewidth=1.2)
    ax2.set_ylabel('LLM Token Consumption', fontsize=10.5, fontweight='bold', color='#1E293B')
    ax2.set_title('LLM Token Expenditure', fontsize=12, fontweight='bold', color='#162A45')
    ax2.set_ylim(0, 22000)
    ax2.grid(axis='y', linestyle='--', alpha=0.6)
    for b in bars2:
        ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 600, f'{int(b.get_height()):,} tokens',
                 ha='center', va='bottom', fontsize=10.5, fontweight='bold', color='#162A45')
    ax2.text(0.5, 14000, '93.9% Fewer\nLLM Tokens', ha='center', fontsize=11, fontweight='bold', color='#0E7490',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#ECFEFF', edgecolor='#0E7490', alpha=0.9))
        
    plt.suptitle('FinOps Economy: Deterministic Pre-Validation vs LLM Brute Force', fontsize=13, fontweight='bold', color='#162A45', y=0.98)
    plt.tight_layout()
    out_path = OUT_DIR / "chart_finops_economy.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print("Saved:", out_path)

# -------------------------------------------------------------
# Chart 4: SRE Incident Resolution MTTR (58m -> 4.2m)
# -------------------------------------------------------------
def plot_mttr_reduction():
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=300)
    
    stages = [
        'Alert Detection\n& Ingestion',
        'Telemetry Retrieval\n& Correlation',
        'Root Cause\nAnalysis (RCA)',
        'Remediation Patch\nSynthesis',
        'Verification &\nDeployment'
    ]
    manual_times = [6.2, 14.5, 24.8, 9.5, 3.4] # Total ~58.4 min
    aipp_times = [0.1, 0.4, 1.8, 1.2, 0.7]       # Total ~4.2 min
    
    x = np.arange(len(stages))
    width = 0.38
    
    r1 = ax.bar(x - width/2, manual_times, width, label='Manual On-Call SRE (Total: 58.4 min)', color='#EF4444', edgecolor='white', linewidth=1.2)
    r2 = ax.bar(x + width/2, aipp_times, width, label='AIPP n8n + PipelineDoctor (Total: 4.2 min)', color='#0D9488', edgecolor='white', linewidth=1.2)
    
    ax.set_ylabel('Stage Duration (Minutes)', fontsize=11, fontweight='bold', color='#1E293B')
    ax.set_title('SRE Incident Triage MTTR: 92.8% Reduction (58.4m -> 4.2m)', fontsize=13, fontweight='bold', color='#162A45', pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(stages, fontsize=9.5, fontweight='bold', color='#1E293B')
    ax.set_ylim(0, 28)
    ax.grid(axis='y', linestyle='--', alpha=0.6)
    ax.legend(loc='upper right', frameon=True, facecolor='#F8FAFC', edgecolor='#CBD5E1', fontsize=10)
    
    # Add values
    for b in r1:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.5, f'{b.get_height():.1f}m', ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#DC2626')
    for b in r2:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.5, f'{b.get_height():.1f}m', ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#0D9488')
        
    plt.tight_layout()
    out_path = OUT_DIR / "chart_mttr_reduction.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print("Saved:", out_path)

if __name__ == "__main__":
    plot_benchmark_sweep()
    plot_latency_speedup()
    plot_finops_economy()
    plot_mttr_reduction()
    print("All viva charts generated successfully!")
