"""Generate the official REVA RACE Capstone Project Final Viva PPTX Deck (15-Slide Master Edition).

Freshly built from scratch strictly adhering to the newly created Capstone Project Report
(Chapters 1–11 + Prelims + Annexures) and live platform capabilities.

Structure (15 Slides):
  Slide 01: Master Title & Candidate Credentials
  Slide 02: Agenda (12 Standardized REVA RACE Sections)
  Slide 03: 01. Introduction & Context (Background & Industry Need)
  Slide 04: 02. Literature Review & Research Gaps (Seminal Works Table)
  Slide 05: 03. Problem Statement (Manual Setup Toil, Syntax Errors, Secret Leaks)
  Slide 06: 04. Objectives of the Study (O1 to O5 with Verified Targets)
  Slide 07: 05. Project Methodology (Figure 5.1 Operational Flow & 3 Stages)
  Slide 08: 06. Resource Specifications (Component Table, K8s, PostgreSQL)
  Slide 09: 07. Software Design (Figure 7.1 Master 5-Tier Architecture HLD)
  Slide 10: 08. Implementation: Multi-Cloud Generator & 8 Agents (Tab 1 & OPA Gates)
  Slide 11: 08. Implementation: PipelineDoctor RCA & Slack HITL (Tab 2, Tab 5 & n8n)
  Slide 12: 09. Testing and Validation (20-Repo Benchmark Sweep & Wilson CI)
  Slide 13: 10. Analysis and Results (50-Incident Corpus & 4-Hour Live Chaos Drill)
  Slide 14: 11. Suggestions and Conclusions (3 Key Takeaways & Live Links)
  Slide 15: 12. Annexure (Reviewer Compliance, References & AI Disclosure)

Outputs:
  - final_deliverable/Subinoy Debnath_CAS_04_Capstone Project_Final PPT_AIPP_Sep_2026.pptx
  - final_deliverable/C_Capstone Project_Final PPT_Subinoy_Debnath_AIPP_Feb_2026.pptx
  - Project_Report_Main/4_CAS_Batch No_Capstone Project_Final PPT_Name_Capstone Short Title_Oct_2025 (2).pptx
  - docs/AIPP_Capstone_Deck.pptx
"""

from __future__ import annotations
import os
from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT_DIR / "final_deliverable" / "images"
SNAPSHOTS_DIR = IMAGES_DIR / "snapshots"
CHARTS_DIR = IMAGES_DIR / "charts"

OUT_TARGETS = [
    ROOT_DIR / "final_deliverable" / "Subinoy Debnath_CAS_04_Capstone Project_Final PPT_AIPP_Sep_2026.pptx",
    ROOT_DIR / "final_deliverable" / "C_Capstone Project_Final PPT_Subinoy_Debnath_AIPP_Feb_2026.pptx",
    ROOT_DIR / "Project_Report_Main" / "4_CAS_Batch No_Capstone Project_Final PPT_Name_Capstone Short Title_Oct_2025 (2).pptx",
    ROOT_DIR / "docs" / "AIPP_Capstone_Deck.pptx",
]

# ---------- Color Palette & Styling ----------
FONT_HEADING = "Roboto Slab"
FONT_BODY = "Arial"

NAVY = RGBColor(0x16, 0x2A, 0x45)       # #162A45 Master Navy
DEEP_BLUE = RGBColor(0x0F, 0x1E, 0x36)  # Deep Navy Background
ACCENT = RGBColor(0xE1, 0x5C, 0x2E)     # #E15C2E Burnt Orange / REVA Accent
CYAN = RGBColor(0x0E, 0x74, 0x90)       # #0E7490 Tech Teal
DARK = RGBColor(0x1E, 0x29, 0x3B)       # #1E293B Slate Dark Text
MUTED = RGBColor(0x64, 0x74, 0x8B)      # #64748B Muted Slate
LIGHT = RGBColor(0xF8, 0xFA, 0xFC)      # #F8FAFC Card Light
LIGHT_BORDER = RGBColor(0xEB, 0xF0, 0xF5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x0D, 0x94, 0x88)      # Success Green

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
TOTAL_SLIDES = 15


def _set_font(run, *, size=13, bold=False, color=DARK, name=FONT_BODY):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def add_rect(slide, left, top, width, height, fill, line=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(1)
    shp.shadow.inherit = False
    return shp


def add_card(slide, left, top, width, height, fill=LIGHT, border=LIGHT_BORDER):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if border is not None:
        shp.line.color.rgb = border
        shp.line.width = Pt(1)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_textbox(slide, left, top, width, height, text, *,
                size=13, bold=False, color=DARK, align=PP_ALIGN.LEFT,
                anchor=MSO_ANCHOR.TOP, name=FONT_BODY):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    _set_font(run, size=size, bold=bold, color=color, name=name)
    return tb


def add_bullets(slide, left, top, width, height, items, *,
                size=11.0, color=DARK, bold_first=False, space_after=6):
    """Clean bullet points formatting 'Keyword: Text' with bold keywords."""
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(space_after)
        if ":" in item and not item.startswith("http"):
            parts = item.split(":", 1)
            run1 = p.add_run()
            run1.text = "• " + parts[0].strip() + ": "
            _set_font(run1, size=size, bold=True, color=color)
            run2 = p.add_run()
            run2.text = parts[1].strip()
            _set_font(run2, size=size, bold=False, color=color)
        else:
            run = p.add_run()
            run.text = "• " + item
            _set_font(run, size=size, color=color, bold=(i == 0 and bold_first))
    return tb


def add_header(slide, section_no, section_title, category=""):
    """Standardized modern slide header aligned with REVA RACE guidelines."""
    if category:
        add_textbox(slide, Inches(0.6), Inches(0.35), Inches(8), Inches(0.3),
                    category.upper(), size=9, bold=True, color=ACCENT, name=FONT_BODY)
    
    add_rect(slide, Inches(0.6), Inches(0.62), Inches(0.42), Inches(0.42), ACCENT)
    add_textbox(slide, Inches(0.6), Inches(0.62), Inches(0.42), Inches(0.42),
                section_no if section_no else "•", size=13, bold=True, color=WHITE,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name=FONT_HEADING)
    
    add_textbox(slide, Inches(1.15), Inches(0.55), Inches(9.5), Inches(0.52),
                section_title, size=21, bold=True, color=NAVY,
                anchor=MSO_ANCHOR.MIDDLE, name=FONT_HEADING)
    
    add_textbox(slide, Inches(9.5), Inches(0.45), Inches(3.2), Inches(0.5),
                "REVA University · RACE", size=11, bold=True, color=MUTED,
                align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                  Inches(0.6), Inches(1.12),
                                  Inches(12.13), Inches(0.015))
    line.fill.solid()
    line.fill.fore_color.rgb = RGBColor(0xCC, 0xD7, 0xE4)
    line.line.fill.background()


def add_footer(slide, page_no, total=TOTAL_SLIDES):
    add_textbox(slide, Inches(0.6), Inches(7.05), Inches(8), Inches(0.3),
                "AIPP: Automated Multi-Cloud CI/CD & DevSecOps Platform  |  MS Capstone Defence",
                size=9, color=MUTED)
    add_textbox(slide, Inches(10.5), Inches(7.05), Inches(2.2), Inches(0.3),
                f"Slide {page_no} of {total}", size=9, bold=True, color=MUTED,
                align=PP_ALIGN.RIGHT)


def add_table(slide, left, top, width, height, headers, rows,
              *, header_fill=NAVY, header_color=WHITE, size=10.0):
    n_rows = len(rows) + 1
    n_cols = len(headers)
    tbl_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = tbl_shape.table
    for i, h_ in enumerate(headers):
        cell = tbl.cell(0, i)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_fill
        cell.text = ""
        p = cell.text_frame.paragraphs[0]
        run = p.add_run()
        run.text = h_
        _set_font(run, size=size, bold=True, color=header_color, name=FONT_HEADING)
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if ri % 2 else LIGHT
            cell.text = ""
            p = cell.text_frame.paragraphs[0]
            run = p.add_run()
            run.text = str(val)
            _set_font(run, size=size, color=DARK)
    return tbl_shape


def add_image_safe(slide, img_path, left, top, width, height):
    if Path(img_path).exists():
        slide.shapes.add_picture(str(img_path), left, top, width, height)
        return True
    return False


def build_fresh_deck():
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # ==========================================================================
    # SLIDE 1: MASTER TITLE SLIDE (Cover Dark Theme)
    # ==========================================================================
    s = blank_slide(prs)
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, NAVY)
    add_rect(s, Inches(0.8), Inches(1.3), Inches(0.8), Inches(0.08), ACCENT)
    
    add_textbox(s, Inches(0.8), Inches(1.5), Inches(11.5), Inches(0.35),
                "REVA ACADEMY FOR CORPORATE EXCELLENCE (RACE) · REVA UNIVERSITY",
                size=12, bold=True, color=ACCENT, name=FONT_HEADING)
    
    add_textbox(s, Inches(0.8), Inches(1.95), Inches(11.8), Inches(1.4),
                "AIPP: Automated Multi-Cloud CI/CD Pipeline\nGeneration & DevSecOps Platform",
                size=33, bold=True, color=WHITE, name=FONT_HEADING)
    
    add_textbox(s, Inches(0.8), Inches(3.55), Inches(11.5), Inches(0.85),
                "An Intelligent Multi-Agent System with 8 Canonical Agents, Pre-Commit Security Guards,\nEvidence-Based Root Cause Analysis & Cryptographically Verified Slack Human-in-the-Loop Approvals",
                size=13.0, color=RGBColor(0xD0, 0xDC, 0xEA))
    
    add_card(s, Inches(0.8), Inches(4.75), Inches(11.7), Inches(2.05), fill=DEEP_BLUE, border=RGBColor(0x2B, 0x47, 0x6E))
    
    add_textbox(s, Inches(1.1), Inches(4.95), Inches(5.2), Inches(1.6),
                "Candidate Information:\n"
                "• Name: Subinoy Debnath\n"
                "• Roll / SRN: CAS-04 / R23EN004\n"
                "• Degree: M.Sc. in Cloud Architecture & Security\n"
                "• Academic Year: Year II (Final Defence, 2026)",
                size=11.5, color=WHITE)
    
    add_textbox(s, Inches(6.6), Inches(4.95), Inches(5.6), Inches(1.6),
                "Supervision & Live Verification:\n"
                "• Institution: REVA University, Bengaluru, India\n"
                "• Review Board: RACE Capstone Review Committee\n"
                "• Live UI Control Tower: http://aipp.dccloud.com\n"
                "• GitHub Code: https://github.com/Subinoy2024/REVA-RACE-CAS04-AIPP-PLATFORM",
                size=11.5, color=WHITE)

    # ==========================================================================
    # SLIDE 2: AGENDA (12 Standardized Sections Mapped Cleanly)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "", "Capstone Presentation Agenda", "Table of Contents")
    
    agenda_items = [
        ("01", "Introduction & Context", "Background, current industry status, why this study"),
        ("02", "Literature Review", "Seminal works, state-of-the-art limitations, research gap"),
        ("03", "Problem Statement", "Technical & functional CI/CD toil, syntax bugs, secret leaks"),
        ("04", "Project Objectives", "5 phased engineering goals (O1–O5) with measurable targets"),
        ("05", "Project Methodology", "Operational execution flow, 3-stage lifecycle, Figure 5.1"),
        ("06", "Resource Specification", "FastAPI, LangGraph, K8s on dck8snode2, PostgreSQL 15"),
        ("07", "Software Design", "5-Tier System Architecture (Figure 7.1 Hero HLD View)"),
        ("08", "Implementation (Generator)", "Tab 1 Generator, 8 canonical agents, 12 OPA Rego rules"),
        ("08", "Implementation (SRE & HITL)", "Tab 2 PipelineDoctor RCA, Tab 5 Slack HITL, 20 n8n flows"),
        ("09", "Testing & Validation", "20-Repo polyglot benchmark sweep (100% pass, Wilson 95% CI)"),
        ("10", "Analysis and Results", "50-incident logs evaluation (F1=0.898) & 4-hour live chaos drill"),
        ("11", "Conclusions & Roadmap", "Key engineering takeaways, Phase 2 roadmap, live access"),
    ]
    
    for i, (num, title, sub) in enumerate(agenda_items):
        col = i // 6
        row = i % 6
        x = Inches(0.8 + col * 6.0)
        y = Inches(1.35 + row * 0.92)
        
        add_card(s, x, y, Inches(5.7), Inches(0.84), fill=LIGHT)
        add_rect(s, x, y, Inches(0.65), Inches(0.84), NAVY)
        add_textbox(s, x, y, Inches(0.65), Inches(0.84), num, size=13, bold=True, color=WHITE,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name=FONT_HEADING)
        add_textbox(s, x + Inches(0.75), y + Inches(0.08), Inches(4.8), Inches(0.35),
                    title, size=11.5, bold=True, color=NAVY, name=FONT_HEADING)
        add_textbox(s, x + Inches(0.75), y + Inches(0.42), Inches(4.8), Inches(0.38),
                    sub, size=9.2, color=MUTED)
    add_footer(s, 2)

    # ==========================================================================
    # SLIDE 3: 01. INTRODUCTION & CONTEXT (Report Chapter 1)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "01", "Introduction: The Challenge of Modern CI/CD", "Industry Context & Motivation")
    
    cards_s3 = [
        ("The Current Industry Reality",
         [
             "Core of Software Delivery: Modern software relies entirely on CI/CD pipelines to build, test, and release code to the cloud.",
             "Cloud Fragmentation: Engineering teams must support AWS, Azure, and GCP simultaneously, each with distinct APIs and IAM roles.",
             "High Operational Friction: Teams maintain brittle YAML scripts across GitHub Actions, GitLab CI, and Azure DevOps by hand.",
         ], Inches(0.8), Inches(1.4), Inches(5.7), Inches(3.9)),
        ("Why Existing Tooling Falls Short",
         [
             "Heavy Manual Burden: Setting up CI/CD for a new microservice takes 4 to 12 hours of senior engineer time.",
             "High Production Risk: Missing spaces or outdated plugins cause silent pipeline crashes in production.",
             "Incident Troubleshooting Toil: When a deployment crashes, SREs spend hours combing through messy log dumps.",
         ], Inches(6.8), Inches(1.4), Inches(5.7), Inches(3.9)),
    ]
    for title, bullets, left, top, w, h in cards_s3:
        add_card(s, left, top, w, h)
        add_textbox(s, left + Inches(0.2), top + Inches(0.2), w - Inches(0.4), Inches(0.35),
                    title, size=13, bold=True, color=NAVY, name=FONT_HEADING)
        add_bullets(s, left + Inches(0.2), top + Inches(0.65), w - Inches(0.4), h - Inches(0.75),
                    bullets, size=11.0, space_after=8)
        
    add_card(s, Inches(0.8), Inches(5.55), Inches(11.7), Inches(1.25), fill=WHITE, border=ACCENT)
    add_textbox(s, Inches(1.1), Inches(5.65), Inches(11.1), Inches(1.05),
                "Project Mission:\n"
                "To build an intelligent, multi-agent platform that automatically writes secure, syntax-verified CI/CD pipelines for any repository and diagnoses deployment failures in seconds—with cryptographic human sign-off before touching production.",
                size=11.5, bold=False, color=DARK)
    add_footer(s, 3)

    # ==========================================================================
    # SLIDE 4: 02. LITERATURE REVIEW & RESEARCH GAPS (Report Chapter 2)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "02", "Literature Review: Seminal Works & Research Gaps", "State-of-the-Art Analysis")
    
    lit_headers = ["Seminal Research Paper", "Core Innovation", "Identified Production Limitation", "How AIPP Bridges the Gap"]
    lit_rows = [
        ("RepoCoder (Zhang et al., 2023)", "Iterative retrieval-augmented code generation", "Passive text generation; no AST validation or cloud policy checks", "Pairs LLM generation with rigid AST parsers and 12 OPA Rego gates"),
        ("AutoGen (Wu et al., 2023)", "Multi-agent conversational workflows", "Open-ended conversational loops; prone to hallucinations & drift", "Enforces a deterministic LangGraph state DAG with strict typed state transitions"),
        ("Rausch et al. (2021)", "Empirical analysis of 4,000+ broken CI builds", "Identified that 28% of failures stem from syntax & secret errors", "Implements 2-pass AST self-healing and regex secret masking at the gateway"),
        ("Accelerate (Forsgren et al., 2018)", "DevOps metrics: Deployment Frequency, Lead Time, MTTR", "Highlights manual triage toil as the primary driver of high MTTR", "PipelineDoctor cuts Mean-Time-To-Diagnose from 45 minutes to < 15 seconds"),
    ]
    add_table(s, Inches(0.8), Inches(1.4), Inches(11.7), Inches(3.6), lit_headers, lit_rows, size=9.5)
    
    add_card(s, Inches(0.8), Inches(5.3), Inches(11.7), Inches(1.5), fill=LIGHT)
    add_textbox(s, Inches(1.0), Inches(5.4), Inches(11.3), Inches(0.35),
                "The Core Research Gap Identified in the Literature", size=12, bold=True, color=NAVY, name=FONT_HEADING)
    gap_bullets = [
        "Missing Deterministic Safety: Existing LLM code tools produce unvalidated text. Nobody combined multi-agent generation with rigid pre-commit AST linters and OPA security policy gates.",
        "Missing Operational Closed-Loop: No platform unified pipeline creation with live incident troubleshooting and cryptographically verified Slack human-in-the-loop approvals.",
    ]
    add_bullets(s, Inches(1.0), Inches(5.8), Inches(11.3), Inches(0.9), gap_bullets, size=10.2, space_after=4)
    add_footer(s, 4)

    # ==========================================================================
    # SLIDE 5: 03. PROBLEM STATEMENT (Report Chapter 3)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "03", "Problem Statement: The Pain of Manual CI/CD & SRE", "Engineering Friction & Security Risks")
    
    problems = [
        ("1. Manual Setup Toil & Burnout",
         [
             "4 to 12 Hours Wasted: Writing boilerplate YAML for every new service is repetitive and error-prone.",
             "Multi-Cloud Fragmentation: Engineers struggle with differing CLI syntaxes across AWS, Azure, and GCP.",
             "DevOps Bottleneck: SREs spend up to 40% of their sprints maintaining brittle scripts instead of building product features.",
         ]),
        ("2. Silent Syntax & IAM Failures",
         [
             "Indentation Bugs: A single missing space breaks the entire pipeline execution at runtime.",
             "Outdated Actions: Deprecated community actions fail during high-stakes production deployments.",
             "Cloud Permission Mismatches: Cloud role and policy misconfigurations stall release cycles for days.",
         ]),
        ("3. Leaked Secrets & High MTTR",
         [
             "Credential Exposure: Developers accidentally commit plaintext API tokens and passwords into Git.",
             "Messy Log Combing: When builds crash, SREs dig through thousands of raw log lines to find the error.",
             "Prolonged Outages: Manual triage delays customer releases and increases production downtime.",
         ]),
    ]
    
    for i, (title, bullets) in enumerate(problems):
        x = Inches(0.8 + i * 4.0)
        add_card(s, x, Inches(1.4), Inches(3.7), Inches(4.0), fill=LIGHT)
        add_rect(s, x, Inches(1.4), Inches(3.7), Inches(0.08), ACCENT)
        add_textbox(s, x + Inches(0.2), Inches(1.6), Inches(3.3), Inches(0.4),
                    title, size=12.5, bold=True, color=NAVY, name=FONT_HEADING)
        add_bullets(s, x + Inches(0.2), Inches(2.1), Inches(3.3), Inches(3.1),
                    bullets, size=10.2, space_after=6)
        
    add_card(s, Inches(0.8), Inches(5.65), Inches(11.7), Inches(1.15), fill=WHITE, border=ACCENT)
    add_textbox(s, Inches(1.1), Inches(5.75), Inches(11.1), Inches(0.95),
                "Formal Problem Statement:\n"
                "How can we automate multi-cloud CI/CD pipeline generation and incident troubleshooting so that every emitted configuration is mathematically syntax-valid, cryptographically secure, and approved by a human before touching production?",
                size=11.5, color=DARK)
    add_footer(s, 5)

    # ==========================================================================
    # SLIDE 6: 04. PROJECT OBJECTIVES (Report Chapter 4)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "04", "Project Objectives: 5 Phased Engineering Goals", "Measurable Scope & Verified Targets")
    
    objectives = [
        ("O1", "Design: Multi-Agent Collaboration Mesh",
         "Architect an 8-agent collaborative system in LangGraph that breaks down repository inspection, planning, drafting, and validation into specialized typed agents.",
         "Verified: 8 canonical agents in cyclic DAG"),
        ("O2", "Build: Multi-Cloud CI/CD Generation",
         "Automatically compile valid pipeline files for GitHub Actions, GitLab CI, and Azure DevOps targeting AWS (EKS), Azure (AKS), and GCP (GKE).",
         "Verified: 20/20 passed across 9 languages"),
        ("O3", "Validate: 12 Pre-Commit Security Policies",
         "Enforce 12 Open Policy Agent (OPA) Rego rules and a 2-pass self-healing AST loop to eliminate leaked secrets, root users, and syntax errors before saving.",
         "Verified: 12 OPA gates + AST self-healing"),
        ("O4", "Diagnose: PipelineDoctor Automated RCA",
         "Diagnose raw crash logs using 1536-d vector search in PostgreSQL (pgvector) to isolate the exact root cause, offending file/line, and verified fix command.",
         "Verified: F1 = 0.898 on 50 real failure logs"),
        ("O5", "Deploy: Live Production Kubernetes System",
         "Deploy the full platform on a live Kubernetes cluster (dck8snode2) with an 8-tab web Control Tower, 20 n8n workflows, and Slack interactive approvals.",
         "Verified: Live on node dck8snode2 in namespace aipp"),
    ]
    
    for i, (code, title, desc, proof) in enumerate(objectives):
        y = Inches(1.35 + i * 1.08)
        add_card(s, Inches(0.8), y, Inches(11.7), Inches(0.98), fill=LIGHT)
        add_rect(s, Inches(0.8), y, Inches(0.9), Inches(0.98), NAVY)
        add_textbox(s, Inches(0.8), y + Inches(0.2), Inches(0.9), Inches(0.6),
                    code, size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER, name=FONT_HEADING)
        add_textbox(s, Inches(1.9), y + Inches(0.08), Inches(6.8), Inches(0.32),
                    title, size=12, bold=True, color=NAVY, name=FONT_HEADING)
        add_textbox(s, Inches(1.9), y + Inches(0.40), Inches(6.8), Inches(0.52),
                    desc, size=10, color=DARK)
        add_card(s, Inches(8.9), y + Inches(0.18), Inches(3.4), Inches(0.62), fill=WHITE, border=GREEN)
        add_textbox(s, Inches(9.0), y + Inches(0.22), Inches(3.2), Inches(0.54),
                    proof, size=9.5, bold=True, color=GREEN)
    add_footer(s, 6)

    # ==========================================================================
    # SLIDE 7: 05. PROJECT METHODOLOGY (Report Chapter 5)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "05", "Project Methodology: 3-Stage Operational Workflow", "System Methodology & Execution Flow")
    
    stages_s7 = [
        ("STAGE 1: CODE INGESTION",
         [
             "Repo Inspection: Reads Git file trees and dependency lockfiles.",
             "Tech Stack Discovery: Detects runtime versions, build tools, and test suites.",
             "Target Selection: User selects target cloud (AWS, Azure, or GCP).",
         ], Inches(0.8), Inches(1.4), Inches(3.7), Inches(2.6)),
        ("STAGE 2: GENERATION & GATES",
         [
             "Agent Drafting: Planner structures stages; Builder writes YAML.",
             "12 OPA Rego Gates: Scans for secrets, root access, and unpinned tags.",
             "Self-Healing AST Loop: Auto-fixes syntax errors in 2 passes.",
         ], Inches(4.8), Inches(1.4), Inches(3.7), Inches(2.6)),
        ("STAGE 3: DELIVERY & SRE",
         [
             "Git PR Creation: Pushes verified pipeline directly to repository.",
             "20 n8n Workflows: Monitors cluster health and processes alerts.",
             "Slack HITL Gate: Requires human sign-off for remediation actions.",
         ], Inches(8.8), Inches(1.4), Inches(3.7), Inches(2.6)),
    ]
    
    for title, bullets, left, top, w, h in stages_s7:
        add_card(s, left, top, w, h)
        add_rect(s, left, top, w, Inches(0.38), NAVY)
        add_textbox(s, left + Inches(0.15), top + Inches(0.06), w - Inches(0.3), Inches(0.3),
                    title, size=10.5, bold=True, color=WHITE, name=FONT_HEADING)
        add_bullets(s, left + Inches(0.2), top + Inches(0.52), w - Inches(0.4), h - Inches(0.6),
                    bullets, size=10.0, space_after=5)
        
    flow_img = IMAGES_DIR / "figure_5_1_platform_flow.png"
    if not flow_img.exists():
        flow_img = IMAGES_DIR / "figure_5_1_methodology.png"
        
    add_card(s, Inches(0.8), Inches(4.2), Inches(11.7), Inches(2.65), fill=WHITE, border=LIGHT_BORDER)
    if flow_img.exists():
        add_image_safe(s, flow_img, Inches(1.0), Inches(4.3), Inches(11.3), Inches(2.45))
    else:
        add_textbox(s, Inches(1.2), Inches(4.8), Inches(10.9), Inches(1.5),
                    "Core Platform Execution Flow:\n"
                    "Developer Git Repo -> Code Inspector -> Planning Agent -> Pipeline Generator -> 12 OPA Gates -> Self-Healing AST Loop -> Verified YAML -> Git PR Creation",
                    size=13, bold=True, color=NAVY)
    add_footer(s, 7)

    # ==========================================================================
    # SLIDE 8: 06. RESOURCE SPECIFICATIONS (Report Chapter 6)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "06", "Resource Requirement Specifications", "Technology Stack & Production Environment")
    
    res_headers = ["Platform Component", "Technology & Version", "Architectural Role in AIPP"]
    res_rows = [
        ("Frontend Web UI", "Gradio 4 (Port 3300)", "Interactive 8-tab Control Tower dashboard (http://aipp.dccloud.com)"),
        ("API Gateway", "FastAPI on Python 3.11", "Zero-Trust credential vault, secret redaction, and Slack webhook receiver"),
        ("Agent Orchestrator", "LangGraph 0.2", "StateGraph coordinating 8 canonical agents with 2-pass AST retry loop"),
        ("Database & Memory", "PostgreSQL 15 + pgvector", "Relational audit logs + 1536-d HNSW cosine vector index for incident solutions"),
        ("Policy & Safety", "Open Policy Agent (OPA)", "12 Rego policies verifying container users, secrets, and cloud configurations"),
        ("Workflow Automation", "n8n Community Edition", "20 active background workflows managing alerts, health, and Slack HITL gates"),
        ("Infrastructure Testbed", "Kubernetes (dck8snode2)", "Ubuntu 22.04 LTS worker node running backend, frontend, and postgres pods"),
        ("Integration Bus", "11 MCP Adapters", "Standardized Model Context Protocol adapters for GitHub, GitLab, K8s, AWS, Azure, GCP"),
    ]
    add_table(s, Inches(0.8), Inches(1.4), Inches(11.7), Inches(4.3), res_headers, res_rows, size=9.5)
    
    add_card(s, Inches(0.8), Inches(5.9), Inches(11.7), Inches(0.9), fill=WHITE, border=GREEN)
    add_textbox(s, Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.7),
                "Production Environment Guarantee: 100% real deployment on live Kubernetes infrastructure (dck8snode2) with zero mock endpoints or simulated data.",
                size=10.5, bold=True, color=DARK)
    add_footer(s, 8)

    # ==========================================================================
    # SLIDE 9: 07. SOFTWARE DESIGN (Report Chapter 7 · Figure 7.1)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "07", "Software Design: 5-Tier Master System Architecture", "High-Level Architecture (Figure 7.1)")
    
    arch_hero = IMAGES_DIR / "figure_7_0_hero.png"
    if not arch_hero.exists():
        arch_hero = IMAGES_DIR / "architecture_hero_drawio.png"
        
    # Left side: 5 Tiers Breakdown
    add_card(s, Inches(0.8), Inches(1.4), Inches(4.8), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(1.0), Inches(1.5), Inches(4.4), Inches(0.35),
                "5-Tier Production Architecture", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    tiers = [
        "1. Presentation Tier: Web Control Tower (Gradio 4 with 8 tabs) and Slack interactive Block-Kit approval cards.",
        "2. Gateway Layer: FastAPI with Zero-Trust security boundary, request rate limiting, and automated secret redaction.",
        "3. Core Agents Mesh: 8 specialized agents working in a LangGraph cyclic state graph with 2-pass AST healing.",
        "4. Dual Memory & Persistence: PostgreSQL 15 for audit logs + pgvector 1536-d HNSW index for past incident solutions.",
        "5. MCP Integration Bus: 11 Model Context Protocol adapters connecting securely to GitHub, GitLab, K8s, AWS, Azure, and GCP.",
    ]
    add_bullets(s, Inches(1.0), Inches(2.0), Inches(4.4), Inches(4.6), tiers, size=10.2, space_after=8)

    # Right side: Official Figure 7.1 Hero Image
    add_card(s, Inches(5.8), Inches(1.4), Inches(6.7), Inches(5.4), fill=WHITE, border=LIGHT_BORDER)
    if arch_hero.exists():
        add_image_safe(s, arch_hero, Inches(5.9), Inches(1.5), Inches(6.5), Inches(5.2))
    else:
        add_textbox(s, Inches(6.2), Inches(3.2), Inches(5.9), Inches(1.5),
                    "[Figure 7.1: Master System Architecture]\nPresentation -> FastAPI Gateway -> LangGraph Agents -> PostgreSQL / pgvector -> MCP Adapters",
                    size=13, color=MUTED, align=PP_ALIGN.CENTER)
    add_footer(s, 9)

    # ==========================================================================
    # SLIDE 10: 08. IMPLEMENTATION - GENERATOR & 8 AGENTS (Report Chapter 8)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "08", "Implementation: Multi-Cloud Generator & 8 Agents", "Control Tower · Tab 1 & Tab 8")
    
    snap_tab1 = SNAPSHOTS_DIR / "tab1_generator_complete.png"
    add_card(s, Inches(0.8), Inches(1.4), Inches(6.3), Inches(5.4), fill=WHITE, border=LIGHT_BORDER)
    if snap_tab1.exists():
        add_image_safe(s, snap_tab1, Inches(0.9), Inches(1.5), Inches(6.1), Inches(5.2))
    else:
        add_textbox(s, Inches(1.5), Inches(3.5), Inches(5.0), Inches(1.0),
                    "[Tab 1 Screenshot: Multi-Cloud Pipeline Generator]", size=13, color=MUTED)

    # Right side: 8 Canonical Agents
    add_card(s, Inches(7.3), Inches(1.4), Inches(5.2), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(7.5), Inches(1.55), Inches(4.8), Inches(0.35),
                "The 8 Canonical Agents in LangGraph", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    agents_list = [
        "1. Repository Analysis Agent: Scans file trees and lockfiles via GitHub/GitLab MCP.",
        "2. Technology Detection Agent: Classifies runtimes, build tools, and test suites.",
        "3. Architecture Detection Agent: Identifies microservices, Dockerfiles, and databases.",
        "4. Pipeline Planning Agent: Synthesizes stage DAG (Build -> Test -> Containerize -> Deploy).",
        "5. Environment Strategy Agent: Maps cloud IAM roles, cluster namespaces, and secrets.",
        "6. Pipeline Generation Agent: Compiles native, deterministic YAML for the target cloud.",
        "7. Validation & Healing Agent: Enforces 12 OPA Rego gates + 2-pass self-healing AST loop.",
        "8. RCA Agent (PipelineDoctor): Asynchronously diagnoses crash logs via pgvector memory.",
    ]
    add_bullets(s, Inches(7.5), Inches(2.0), Inches(4.8), Inches(4.6), agents_list, size=9.8, space_after=5)
    add_footer(s, 10)

    # ==========================================================================
    # SLIDE 11: 08. IMPLEMENTATION - PIPELINEDOCTOR & SLACK HITL (Report Chapter 8)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "08", "Implementation: PipelineDoctor RCA & Slack HITL", "Control Tower · Tab 2 & Tab 5")
    
    # Left Card: PipelineDoctor
    add_card(s, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(1.0), Inches(1.55), Inches(5.3), Inches(0.35),
                "PipelineDoctor: Evidence-Grounded RCA (Tab 2)", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    doctor_bullets = [
        "Ingests Raw Crash Logs: Accepts 500+ line messy crash dumps from Kubernetes pods or CI builds.",
        "pgvector Semantic Search: Matches errors against 1536-d historical embeddings in PostgreSQL.",
        "Plain-English Root Cause: Explains exactly why the failure occurred without confusing jargon.",
        "Offending File & Line: Pinpoints the specific code file, Dockerfile, or manifest line causing the crash.",
        "Copy-Paste Fix Command: Gives engineers the exact shell command or configuration patch.",
    ]
    add_bullets(s, Inches(1.0), Inches(2.0), Inches(5.3), Inches(2.8), doctor_bullets, size=10.2, space_after=6)
    
    snap_tab2 = SNAPSHOTS_DIR / "tab3_pipelinedoctor_rca.png"
    if snap_tab2.exists():
        add_image_safe(s, snap_tab2, Inches(1.0), Inches(4.7), Inches(5.3), Inches(1.95))

    # Right Card: Slack HITL & n8n
    add_card(s, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(7.0), Inches(1.55), Inches(5.3), Inches(0.35),
                "Slack Human-in-the-Loop & n8n Engine (Tab 5)", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    slack_bullets = [
        "n8n Workflow #16 HITL Gate: n8n receives validated pipelines/alerts and holds at a Wait node.",
        "Interactive Block-Kit Card: Posts rich card to Slack with incident summary and Approve/Reject buttons.",
        "Human Decision: Engineers review the context and click Approve or Reject directly in Slack.",
        "HMAC-SHA256 Security: FastAPI (backend/api/slack.py) cryptographically verifies every button click.",
        "Full Audit Ledger: Decisions are recorded in PostgreSQL audit_logs before releasing changes.",
    ]
    add_bullets(s, Inches(7.0), Inches(2.0), Inches(5.3), Inches(2.8), slack_bullets, size=10.2, space_after=6)
    
    snap_slack = SNAPSHOTS_DIR / "tab5_slack_card.png"
    if snap_slack.exists():
        add_image_safe(s, snap_slack, Inches(7.1), Inches(4.85), Inches(5.1), Inches(1.8))
    add_footer(s, 11)

    # ==========================================================================
    # SLIDE 12: 09. TESTING AND VALIDATION (Report Chapter 9)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "09", "Testing & Validation: 20-Repository Benchmark Sweep", "Empirical Evaluation Across 9 Languages")
    
    # Left side: Clean Chart with zero label overlap
    chart_clean = CHARTS_DIR / "chart_benchmark_sweep_clean.png"
    if not chart_clean.exists():
        chart_clean = CHARTS_DIR / "chart_benchmark_sweep.png"
        
    add_card(s, Inches(0.8), Inches(1.4), Inches(6.8), Inches(5.4), fill=WHITE, border=LIGHT_BORDER)
    if chart_clean.exists():
        add_image_safe(s, chart_clean, Inches(0.9), Inches(1.5), Inches(6.6), Inches(5.2))
    else:
        add_textbox(s, Inches(1.5), Inches(3.5), Inches(5.5), Inches(1.0),
                    "[20-Repository Benchmark Sweep Chart]", size=13, color=MUTED)

    # Right side: Metric Cards
    add_card(s, Inches(7.8), Inches(1.4), Inches(4.7), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(8.0), Inches(1.55), Inches(4.3), Inches(0.35),
                "Benchmark Verification Rigor", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    test_metrics = [
        "20 / 20 Repositories Passed: 100.0% pass rate across 9 language ecosystems (Python, Go, Node.js, Java, Rust, C#, Kotlin, PHP, Ruby).",
        "First-Pass vs. Self-Healed: 16 pipelines passed on initial generation; 4 pipelines with minor syntax issues were automatically corrected by the 2nd-pass AST self-healing loop.",
        "Wilson Score 95% CI: [83.9%, 100.0%] statistical confidence guarantee, comfortably exceeding the >= 80% thesis target.",
        "52 Automated Unit Tests: pytest suites testing API endpoints, AST generators, and security rules with 100% pass rate.",
        "12 OPA Rego Security Gates: 0 secrets leaked, 0 root users allowed, 0 unpinned container tags admitted.",
    ]
    add_bullets(s, Inches(8.0), Inches(2.05), Inches(4.3), Inches(4.5), test_metrics, size=10.2, space_after=8)
    add_footer(s, 12)

    # ==========================================================================
    # SLIDE 13: 10. ANALYSIS AND RESULTS (Report Chapter 10)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "10", "Analysis & Results: SRE Incident Corpus & Chaos Drill", "Diagnostic Accuracy & Production Resilience")
    
    # Left Card: 50-Incident Evaluation Corpus
    add_card(s, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(1.0), Inches(1.55), Inches(5.3), Inches(0.35),
                "50-Incident Evaluation Corpus", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    incident_bullets = [
        "Real Failure Data: Evaluated against 50 authentic failure logs spanning Kubernetes OOMKills, image pull errors, and CI runner timeouts.",
        "Diagnostic Accuracy: PipelineDoctor achieved an F1-Score of 0.898 (89.8% precision/recall).",
        "Empirical Lift over Raw AI: Significantly outperformed baseline raw LLM prompting (F1 = 0.720, p < 0.01).",
        "Zero Hallucinated Fixes: 1536-d pgvector historical grounding ensured that every recommended fix was anchored in real runbooks.",
        "MTTD Reduction: Slashed Mean-Time-To-Diagnose from 45 minutes of manual log inspection to under 15 seconds.",
    ]
    add_bullets(s, Inches(1.0), Inches(2.05), Inches(5.3), Inches(4.4), incident_bullets, size=10.5, space_after=8)

    # Right Card: 4-Hour Live Chaos Stress Drill
    add_card(s, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.4), fill=LIGHT)
    add_textbox(s, Inches(7.0), Inches(1.55), Inches(5.3), Inches(0.35),
                "4-Hour Live Kubernetes Stress Drill", size=13, bold=True, color=NAVY, name=FONT_HEADING)
    
    chaos_bullets = [
        "Live Stress Test: Ran a continuous 4-hour chaos exercise on live Kubernetes worker node dck8snode2.",
        "Fault Injection: Intentionally killed backend pods, induced high memory pressure, and triggered alert storms.",
        "Automated Error Routing: Prometheus alerts immediately routed to n8n workflows and triggered PipelineDoctor.",
        "Slack Approval Verification: Approval cards posted reliably to Slack; HMAC signatures prevented unauthorized button clicks.",
        "Zero Credential Leakage: PostgreSQL audit log verification confirmed zero secrets were logged in plaintext.",
    ]
    add_bullets(s, Inches(7.0), Inches(2.05), Inches(5.3), Inches(2.7), chaos_bullets, size=10.2, space_after=6)
    
    snap_k8s = SNAPSHOTS_DIR / "live_k8s_cluster.png"
    if snap_k8s.exists():
        add_card(s, Inches(7.0), Inches(4.85), Inches(5.3), Inches(1.8), fill=DARK, border=None)
        add_image_safe(s, snap_k8s, Inches(7.05), Inches(4.9), Inches(5.2), Inches(1.7))
    add_footer(s, 13)

    # ==========================================================================
    # SLIDE 14: 11. SUGGESTIONS AND CONCLUSIONS (Report Chapter 11)
    # ==========================================================================
    s = blank_slide(prs)
    add_header(s, "11", "Suggestions and Conclusions: Engineering Takeaways", "Key Insights, Roadmap & Live Project Access")
    
    takeaways = [
        ("1. Deterministic Guardrails Beat Raw AI",
         "Generative AI is great at drafting structure, but production CI/CD requires mathematical exactness. Pairing LLM generation with rigid AST parsers and 12 OPA security gates eliminates syntax failures and security vulnerabilities.",
         NAVY),
        ("2. Semantic Memory Eliminates Repeat Toil",
         "When an incident happens, chances are someone has solved it before. Storing historical resolutions in a 1536-d vector database (pgvector) allows PipelineDoctor to diagnose crashes in seconds with 89.8% precision.",
         CYAN),
        ("3. Human Control Drives Trust and Adoption",
         "Engineers reject 'black-box' automation that modifies production unannounced. Providing clear plain-English reasoning and one-click Slack approval cards with cryptographic verification builds lasting trust.",
         ACCENT),
    ]
    
    for i, (title, text, col) in enumerate(takeaways):
        y = Inches(1.4 + i * 1.55)
        add_card(s, Inches(0.8), y, Inches(11.7), Inches(1.4), fill=LIGHT)
        add_rect(s, Inches(0.8), y, Inches(0.18), Inches(1.4), col)
        add_textbox(s, Inches(1.15), y + Inches(0.12), Inches(11.1), Inches(0.32),
                    title, size=12.5, bold=True, color=col, name=FONT_HEADING)
        add_textbox(s, Inches(1.15), y + Inches(0.48), Inches(11.1), Inches(0.82),
                    text, size=10.5, color=DARK)
        
    add_card(s, Inches(0.8), Inches(6.15), Inches(11.7), Inches(0.75), fill=WHITE, border=GREEN)
    add_textbox(s, Inches(1.0), Inches(6.22), Inches(11.3), Inches(0.6),
                "Live Project Access: Web UI: http://aipp.dccloud.com  |  API Health: http://api-aipp.dccloud.com/api/health\n"
                "GitHub Repository: https://github.com/Subinoy2024/REVA-RACE-CAS04-AIPP-PLATFORM  (All 5 Objectives Met & Verified)",
                size=10.5, bold=True, color=DARK)
    add_footer(s, 14)

    # ==========================================================================
    # SLIDE 15: 12. ANNEXURE (Report Annexures & Compliance)
    # ==========================================================================
    s = blank_slide(prs)
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, NAVY)
    add_rect(s, Inches(0.8), Inches(1.2), Inches(0.8), Inches(0.08), ACCENT)
    
    add_textbox(s, Inches(0.8), Inches(1.4), Inches(11.5), Inches(0.35),
                "CAPSTONE PROJECT DEFENCE · REVA UNIVERSITY",
                size=12, bold=True, color=ACCENT, name=FONT_HEADING)
    
    add_textbox(s, Inches(0.8), Inches(1.85), Inches(11.5), Inches(0.7),
                "12. Annexure: Compliance, References & Project Close",
                size=28, bold=True, color=WHITE, name=FONT_HEADING)
    
    # Left Card: Reviewer Compliance & Integrity
    add_card(s, Inches(0.8), Inches(2.75), Inches(5.7), Inches(3.9), fill=DEEP_BLUE, border=RGBColor(0x2B, 0x47, 0x6E))
    add_textbox(s, Inches(1.0), Inches(2.9), Inches(5.3), Inches(0.35),
                "Reviewer Compliance & Academic Integrity", size=13, bold=True, color=WHITE, name=FONT_HEADING)
    
    annex_bullets = [
        "Reviewer Feedback Compliance: All 9 major reviewer recommendations (Wilson Score CI, decoupled generation boundary, 2-pass AST retry, HMAC-SHA256 verifier, authentic code snippets) fully incorporated.",
        "Plagiarism & Similarity Index: Fully compliant with REVA RACE threshold (< 10% similarity).",
        "AI Tool Usage Disclosure: Transparent disclosure of AI assistive tools for syntax linting and diagram rendering.",
        "100% Verbatim Real Code: All code snippets in Chapter 8 verified against real production files with exact line numbers.",
    ]
    add_bullets(s, Inches(1.0), Inches(3.35), Inches(5.3), Inches(3.1), annex_bullets, size=10.2, color=WHITE, space_after=6)

    # Right Card: Key References & Thank You
    add_card(s, Inches(6.8), Inches(2.75), Inches(5.7), Inches(3.9), fill=DEEP_BLUE, border=RGBColor(0x2B, 0x47, 0x6E))
    add_textbox(s, Inches(7.0), Inches(2.9), Inches(5.3), Inches(0.35),
                "Key References & Closing", size=13, bold=True, color=WHITE, name=FONT_HEADING)
    
    ref_bullets = [
        "[1] N. Forsgren et al., Accelerate: Building High Performing Tech Organizations, IT Revolution, 2018.",
        "[2] F. Zhang et al., 'RepoCoder: Repository-Level Code Completion Through Iterative Retrieval,' NeurIPS 2023.",
        "[3] Q. Wu et al., 'AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation,' arXiv:2308.08155, 2023.",
        "[4] T. Rausch et al., 'An Empirical Analysis of Build Failures in Continuous Integration,' IEEE TSE, 2021.",
        "Candidate: Subinoy Debnath (Roll: CAS-04 / SRN: R23EN004)",
        "Degree: M.Sc. in Cloud Architecture & Security, REVA University",
    ]
    add_bullets(s, Inches(7.0), Inches(3.35), Inches(5.3), Inches(2.3), ref_bullets, size=10.0, color=WHITE, space_after=5)
    
    add_card(s, Inches(7.0), Inches(5.8), Inches(5.3), Inches(0.65), fill=ACCENT, border=None)
    add_textbox(s, Inches(7.0), Inches(5.85), Inches(5.3), Inches(0.55),
                "Thank You! Questions & Discussion Welcomed.", size=13, bold=True, color=WHITE,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name=FONT_HEADING)
    
    add_textbox(s, Inches(0.8), Inches(6.85), Inches(11.7), Inches(0.3),
                "REVA University · RACE · Master of Science in Cloud Architecture & Security · Final Viva Defense 2026",
                size=9.5, color=RGBColor(0xA0, 0xB4, 0xCC), align=PP_ALIGN.CENTER)

    # Save presentation to all output targets
    for target in OUT_TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(target))
        print(f"Saved: {target} (Size: {target.stat().st_size / (1024 * 1024):.2f} MB)")


if __name__ == "__main__":
    build_fresh_deck()
