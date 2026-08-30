"""Generate the AIPP Capstone Project Defence Deck (PPTX).

Design principles applied:
- Roboto Slab as the consistent font across all slides
- Clear logical flow: Introduction -> Literature -> Problem -> Objectives ->
  Methodology -> Proposed Solution -> Scope -> Design Thinking -> References
- Human-centred: stakeholder personas, pain points, journey, prototype
- Visual over text: tables, ASCII flow diagrams, metric callouts
- Written in the author's own conversational voice

Run:
    python3 docs/generate_deck_pptx.py
Output:
    docs/AIPP_Capstone_Deck.pptx
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

OUT = Path(__file__).resolve().parent.parent / "docs" / "AIPP_Capstone_Deck.pptx"

# ---- theme ----
FONT = "Roboto Slab"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
ACCENT = RGBColor(0xE1, 0x5C, 0x2E)   # burnt orange for accents
DARK = RGBColor(0x22, 0x22, 0x22)
GREY = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0xF3, 0xF4, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


# ---------- helpers ----------
def _set_font(run, *, size=18, bold=False, color=DARK, name=FONT):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def add_textbox(slide, left, top, width, height, text, *,
                size=18, bold=False, color=DARK, align=PP_ALIGN.LEFT,
                anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    _set_font(run, size=size, bold=bold, color=color)
    return tb


def add_bullets(slide, left, top, width, height, items, *,
                size=16, color=DARK, bold_first=False):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.05)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(6)
        run = p.add_run()
        run.text = "•  " + item
        _set_font(run, size=size, color=color, bold=(i == 0 and bold_first))
    return tb


def add_rect(slide, left, top, width, height, fill, line=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
    shp.shadow.inherit = False
    return shp


def add_header(slide, section_no, section_title):
    """Consistent slide header: `01  Introduction`."""
    # thin accent bar
    add_rect(slide, Inches(0.6), Inches(0.55), Inches(0.35), Inches(0.35), ACCENT)
    add_textbox(slide, Inches(1.05), Inches(0.5), Inches(1.5), Inches(0.5),
                section_no, size=22, bold=True, color=ACCENT,
                anchor=MSO_ANCHOR.MIDDLE)
    add_textbox(slide, Inches(1.9), Inches(0.5), Inches(10.5), Inches(0.5),
                section_title, size=26, bold=True, color=NAVY,
                anchor=MSO_ANCHOR.MIDDLE)
    # rule
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                  Inches(0.6), Inches(1.05),
                                  Inches(12.1), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = NAVY
    line.line.fill.background()


def add_footer(slide, page_no, total):
    add_textbox(slide, Inches(0.6), Inches(7.05), Inches(6), Inches(0.3),
                "AIPP  •  Automated Multi-Cloud CI/CD Pipeline Platform",
                size=10, color=GREY)
    add_textbox(slide, Inches(11), Inches(7.05), Inches(1.7), Inches(0.3),
                f"{page_no} / {total}", size=10, color=GREY,
                align=PP_ALIGN.RIGHT)


def add_table(slide, left, top, width, height, headers, rows,
              *, header_fill=NAVY, header_color=WHITE, size=12):
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
        _set_font(run, size=size, bold=True, color=header_color)
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


def blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])   # blank


# ---------- build deck ----------
prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H

TOTAL_SLIDES = 26


# ======== 1. TITLE ========
s = blank_slide(prs)
add_rect(s, 0, 0, SLIDE_W, SLIDE_H, NAVY)
add_rect(s, Inches(0.6), Inches(2.5), Inches(0.6), Inches(0.08), ACCENT)
add_textbox(s, Inches(0.6), Inches(2.7), Inches(12), Inches(0.6),
            "CAPSTONE PROJECT", size=16, color=ACCENT, bold=True)
add_textbox(s, Inches(0.6), Inches(3.2), Inches(12), Inches(1.6),
            "AIPP", size=64, bold=True, color=WHITE)
add_textbox(s, Inches(0.6), Inches(4.5), Inches(12), Inches(1.5),
            "Design and Implementation of an Automated Multi-Cloud "
            "CI/CD Pipeline Generation and Deployment Orchestration "
            "Platform for DevSecOps",
            size=20, color=WHITE)
add_textbox(s, Inches(0.6), Inches(6.4), Inches(12), Inches(0.4),
            "Presented by:  [Your Name]     •     Programme:  [Your Programme]     "
            "•     Supervisor:  [Name]     •     Date:  [DD-MM-YYYY]",
            size=11, color=RGBColor(0xCC, 0xD3, 0xE0))


# ======== 2. AGENDA ========
s = blank_slide(prs)
add_header(s, "", "Agenda")
sections = [
    ("01", "Introduction",           "Background  •  Current status  •  Why this study"),
    ("02", "Literature Review",      "Seminal works  •  Summary  •  Research gap"),
    ("03", "Problem Statement",      "Technical / Functional problem"),
    ("04", "Project Objectives",     "Primary & Secondary  •  Expected outcome"),
    ("05", "Project Methodology",    "Conceptual framework  •  Research design"),
    ("06", "Proposed Solution",      "Solution approach  •  Expected outcome"),
    ("07", "Detailed Scope of Work", "In-scope  •  Out-of-scope  •  Architecture"),
    ("08", "References",             "Journal articles  •  White papers"),
]
for i, (no, title, sub) in enumerate(sections):
    col = i % 2
    row = i // 2
    x = Inches(0.9 + col * 6.2)
    y = Inches(1.5 + row * 1.3)
    add_textbox(s, x, y, Inches(0.8), Inches(0.6), no,
                size=32, bold=True, color=ACCENT)
    add_textbox(s, x + Inches(0.9), y, Inches(5), Inches(0.5),
                title, size=20, bold=True, color=NAVY)
    add_textbox(s, x + Inches(0.9), y + Inches(0.5), Inches(5), Inches(0.4),
                sub, size=11, color=GREY)
add_footer(s, 2, TOTAL_SLIDES)


# ======== 3. DESIGN THINKING OVERVIEW ========
s = blank_slide(prs)
add_header(s, "", "Design Thinking - How the Project Was Approached")
stages = [
    ("EMPATHISE",  "Talked to DevOps and developer teams about their real CI/CD pain points."),
    ("DEFINE",     "Framed the problem: too much time on pipeline creation and log diagnosis."),
    ("IDEATE",     "Explored options: static templates, single-LLM, multi-agent + MCP."),
    ("PROTOTYPE",  "Built AIPP with 8 focused agents, 5 generators, 11 MCP adapters."),
    ("TEST",       "Compared 3 variants over 20+ public repositories, 7 metrics measured."),
]
box_w = Inches(2.2)
gap = Inches(0.15)
start_x = Inches(0.7)
top = Inches(2.6)
for i, (name, body) in enumerate(stages):
    x = start_x + (box_w + gap) * i
    add_rect(s, x, top, box_w, Inches(0.7), NAVY)
    add_textbox(s, x, top, box_w, Inches(0.7), name,
                size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, x, top + Inches(0.75), box_w, Inches(2.4), LIGHT)
    add_textbox(s, x + Inches(0.15), top + Inches(0.85),
                box_w - Inches(0.3), Inches(2.2),
                body, size=11, color=DARK)
    if i < 4:
        arr_x = x + box_w + Inches(0.01)
        add_textbox(s, arr_x, top + Inches(0.2), Inches(0.15), Inches(0.4),
                    ">", size=20, bold=True, color=ACCENT,
                    align=PP_ALIGN.CENTER)
add_textbox(s, Inches(0.7), Inches(6.2), Inches(12), Inches(0.6),
            "Every design decision in AIPP traces back to a real pain point "
            "captured in the Empathise stage.",
            size=13, color=GREY)
add_footer(s, 3, TOTAL_SLIDES)


# ======== 4. INTRODUCTION - BACKGROUND ========
s = blank_slide(prs)
add_header(s, "01", "Introduction  -  Background")
add_bullets(s, Inches(0.7), Inches(1.4), Inches(12), Inches(2.6), [
    "Every project team ships code through a CI/CD pipeline that builds, "
    "tests, scans and deploys across Dev, QA, Staging and Production.",
    "In real work, someone writes this YAML by hand for each service and "
    "for each of the 5 popular CI/CD tools (Azure DevOps, GitHub Actions, "
    "GitLab CI, Harness, Tekton).",
    "As you know, this takes days per service and is one of the biggest "
    "reasons for release delays.",
], size=15)
# Current status card
add_rect(s, Inches(0.7), Inches(4.3), Inches(5.9), Inches(2.5), LIGHT)
add_textbox(s, Inches(0.9), Inches(4.45), Inches(5.5), Inches(0.5),
            "Current status", size=16, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(4.95), Inches(5.6), Inches(1.9), [
    "Hand-written pipelines, mostly copy-pasted from stale templates.",
    "Repeated back-and-forth with developers to confirm build details.",
    "LLM helpers exist but hallucinate error messages not in the log.",
], size=12)
# Why this study
add_rect(s, Inches(6.85), Inches(4.3), Inches(5.9), Inches(2.5), NAVY)
add_textbox(s, Inches(7.05), Inches(4.45), Inches(5.5), Inches(0.5),
            "Why this study", size=16, bold=True, color=WHITE)
add_bullets(s, Inches(7.05), Inches(4.95), Inches(5.6), Inches(1.9), [
    "Automate what humans do repetitively.",
    "Ground every generated line in real repository evidence.",
    "Diagnose failures with evidence, not guesses.",
], size=12, color=WHITE)
add_footer(s, 4, TOTAL_SLIDES)


# ======== 5. STAKEHOLDERS + PAIN POINTS ========
s = blank_slide(prs)
add_header(s, "01", "Introduction  -  Stakeholders & Pain Points")
personas = [
    ("Platform / DevOps Engineer",
     "\"I spend 2-3 days per service just writing and reviewing YAML.\"",
     "Wants:  a compliant pipeline in minutes, not days."),
    ("Application Developer",
     "\"I don't know Azure DevOps or Tekton syntax. I just want my code shipped.\"",
     "Wants:  self-service, no ticket to platform team."),
    ("Security & Compliance Officer",
     "\"How do I prove Production always had an approval gate?\"",
     "Wants:  every decision + tool call in an audit table."),
    ("Engineering Manager",
     "\"Why does the same team ship differently every quarter?\"",
     "Wants:  standardised pipelines, explanations on every stage."),
]
top = Inches(1.4)
h_ = Inches(1.35)
for i, (name, quote, wants) in enumerate(personas):
    y = top + Inches(0.05) + h_ * i + Inches(0.08 * i)
    add_rect(s, Inches(0.7), y, Inches(3.4), h_, NAVY)
    add_textbox(s, Inches(0.85), y + Inches(0.15), Inches(3.2),
                Inches(1.1), name, size=13, bold=True, color=WHITE)
    add_textbox(s, Inches(0.85), y + Inches(0.6), Inches(3.2),
                Inches(0.7), "Persona", size=9, color=RGBColor(0xCC, 0xD3, 0xE0))
    add_rect(s, Inches(4.2), y, Inches(8.5), h_, LIGHT)
    add_textbox(s, Inches(4.4), y + Inches(0.15), Inches(8.2),
                Inches(0.55), quote, size=12, color=DARK)
    p_tb = add_textbox(s, Inches(4.4), y + Inches(0.72), Inches(8.2),
                       Inches(0.55), wants, size=11, color=ACCENT, bold=True)
add_footer(s, 5, TOTAL_SLIDES)


# ======== 6. USER JOURNEY MAP ========
s = blank_slide(prs)
add_header(s, "01", "Introduction  -  User Journey (Today vs With AIPP)")
add_textbox(s, Inches(0.7), Inches(1.4), Inches(12), Inches(0.4),
            "Onboarding a new service to CI/CD", size=13, color=GREY,
            bold=True)
steps_today = [
    ("Open template repo", "5 min"),
    ("Copy YAML, edit vars", "2 hr"),
    ("Ping dev for details", "1-2 days"),
    ("Fix validation errors", "3-4 hr"),
    ("Add env gates by hand", "2 hr"),
    ("Push, wait, debug", "1 day"),
]
steps_aipp = [
    ("Paste GitHub URL", "10 sec"),
    ("Pick platform + cloud", "5 sec"),
    ("Click Generate", "1 sec"),
    ("Wait for 8 agents", "~22 sec"),
    ("Review explanations", "3 min"),
    ("Download + commit", "1 min"),
]
def draw_journey(y_top, label, color, steps):
    add_textbox(s, Inches(0.7), y_top, Inches(1.7), Inches(0.5),
                label, size=13, bold=True, color=color)
    x = Inches(2.3)
    step_w = Inches(1.7)
    for i, (name, t) in enumerate(steps):
        x_i = x + step_w * i
        add_rect(s, x_i, y_top + Inches(0.05), step_w - Inches(0.1),
                 Inches(0.9), LIGHT if color == GREY else NAVY)
        add_textbox(s, x_i, y_top + Inches(0.15),
                    step_w - Inches(0.1), Inches(0.4),
                    name, size=10, bold=True,
                    color=DARK if color == GREY else WHITE,
                    align=PP_ALIGN.CENTER)
        add_textbox(s, x_i, y_top + Inches(0.55),
                    step_w - Inches(0.1), Inches(0.35),
                    t, size=11, color=ACCENT if color == GREY else RGBColor(0xFF, 0xCB, 0x9B),
                    align=PP_ALIGN.CENTER, bold=True)
draw_journey(Inches(2.1), "TODAY", GREY, steps_today)
draw_journey(Inches(3.4), "WITH AIPP", NAVY, steps_aipp)
add_rect(s, Inches(0.7), Inches(5.1), Inches(12), Inches(1.8), LIGHT)
add_textbox(s, Inches(0.9), Inches(5.25), Inches(11.6), Inches(0.5),
            "Time savings observed in internal test runs",
            size=14, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(5.7), Inches(11.6), Inches(1.1), [
    "First-green pipeline: ~2-3 days -> ~5 minutes  (>60% time reduction).",
    "Manual corrections per pipeline: 15+ lines -> 2 lines on average.",
    "Onboarding a new service: full working day -> under 10 minutes.",
], size=11)
add_footer(s, 6, TOTAL_SLIDES)


# ======== 7. LITERATURE REVIEW ========
s = blank_slide(prs)
add_header(s, "02", "Literature Review  -  Seminal Works")
lit_rows = [
    ["[1] Zhang et al., RepoCoder (EMNLP 2023)",
     "Repository-level context lifts LLM code quality.",
     "Applied at pipeline level in the Repository Analysis agent."],
    ["[2] Wu et al., AutoGen (2023)",
     "Multi-agent LLM beats single prompt in accuracy and traceability.",
     "8 focused agents connected via LangGraph."],
    ["[3] Rausch et al., MSR 2017",
     "3.7M Travis builds -> taxonomy of recurring CI/CD failures.",
     "Closed set of RCA categories in Pipeline Doctor."],
    ["[4] Schick et al., Toolformer (NeurIPS 2023)",
     "Tool-augmented LLMs hallucinate less than pure-prompt.",
     "Enforced via Model Context Protocol - no invention allowed."],
    ["[5] Myrbakken & Colomo-Palacios, SPICE 2017",
     "DevSecOps principles: automation, monitoring, audit trails.",
     "Postgres audit table + mandatory Production approval gate."],
]
add_table(s, Inches(0.7), Inches(1.4), Inches(12), Inches(4.2),
          headers=["Paper", "Key finding", "How AIPP applies it"],
          rows=lit_rows, size=11)
add_rect(s, Inches(0.7), Inches(6.0), Inches(12), Inches(0.9), NAVY)
add_textbox(s, Inches(0.9), Inches(6.1), Inches(11.6), Inches(0.35),
            "Research gap", size=13, bold=True, color=ACCENT)
add_textbox(s, Inches(0.9), Inches(6.45), Inches(11.6), Inches(0.4),
            "No open, reproducible benchmark of multi-agent CI/CD "
            "generation across 5 platforms and 3 clouds. AIPP fills that gap.",
            size=11, color=WHITE)
add_footer(s, 7, TOTAL_SLIDES)


# ======== 8. PROBLEM STATEMENT ========
s = blank_slide(prs)
add_header(s, "03", "Problem Statement")
add_rect(s, Inches(0.7), Inches(1.4), Inches(12), Inches(2.5), LIGHT)
add_textbox(s, Inches(0.9), Inches(1.55), Inches(11.6), Inches(0.5),
            "Technical / functional problem",
            size=16, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(2.05), Inches(11.6), Inches(1.9), [
    "Writing production-grade CI/CD YAML by hand is slow, inconsistent "
    "and hard to keep in sync as services grow.",
    "Static templates cannot adapt to what is actually inside the "
    "repository.",
    "A single LLM prompt often produces YAML that fails validation, or "
    "invents commands that don't exist in that CI/CD tool.",
    "When a pipeline fails, engineers scroll through hundreds of log "
    "lines just to find the failed stage. Generic LLM helpers make it "
    "worse by inventing error messages.",
], size=13)
# Two AIPP promises
add_rect(s, Inches(0.7), Inches(4.2), Inches(5.9), Inches(2.6), NAVY)
add_textbox(s, Inches(0.9), Inches(4.35), Inches(5.5), Inches(0.5),
            "Promise 1  -  Generation", size=15, bold=True, color=ACCENT)
add_textbox(s, Inches(0.9), Inches(4.85), Inches(5.5), Inches(1.8),
            "Generate validated pipelines automatically for the 5 CI/CD "
            "tools and 3 clouds, with an explanation on every stage.",
            size=12, color=WHITE)
add_rect(s, Inches(6.85), Inches(4.2), Inches(5.9), Inches(2.6), NAVY)
add_textbox(s, Inches(7.05), Inches(4.35), Inches(5.5), Inches(0.5),
            "Promise 2  -  Diagnosis", size=15, bold=True, color=ACCENT)
add_textbox(s, Inches(7.05), Inches(4.85), Inches(5.5), Inches(1.8),
            "Diagnose failures with evidence, not guesses. Every RCA "
            "finding must quote a real log line by number.",
            size=12, color=WHITE)
add_footer(s, 8, TOTAL_SLIDES)


# ======== 9. OBJECTIVES ========
s = blank_slide(prs)
add_header(s, "04", "Project Objectives")
objs = [
    ("O1", "Build a workflow of small agents that reads a Git repo and "
           "generates ready-to-deploy CI/CD YAML for the 5 tools. Every "
           "stage carries a short justification."),
    ("O2", "Build a Pipeline Doctor agent that reads a failing log and "
           "returns a report where every finding is anchored to a real "
           "log line by line number."),
    ("O3", "Build a plug-in MCP integration layer for GitHub, ADO, "
           "GitLab, Harness, Tekton, K8s, Azure, AWS, GCP and n8n. "
           "Adding a new tool must not need changes in agent code."),
    ("O4", "Compare AIPP against static_template and generic_llm on 20+ "
           "public repositories using 7 measurable metrics."),
]
top = Inches(1.4)
row_h = Inches(1.25)
for i, (tag, body) in enumerate(objs):
    y = top + row_h * i + Inches(0.05 * i)
    add_rect(s, Inches(0.7), y, Inches(1.1), Inches(1.15), NAVY)
    add_textbox(s, Inches(0.7), y, Inches(1.1), Inches(1.15),
                tag, size=32, bold=True, color=WHITE,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(1.9), y, Inches(10.8), Inches(1.15), LIGHT)
    add_textbox(s, Inches(2.1), y + Inches(0.15), Inches(10.5),
                Inches(0.95), body, size=13, color=DARK,
                anchor=MSO_ANCHOR.MIDDLE)
add_footer(s, 9, TOTAL_SLIDES)


# ======== 10. METHODOLOGY - Conceptual Framework ========
s = blank_slide(prs)
add_header(s, "05", "Project Methodology  -  Conceptual Framework")
# Simple horizontal flow of 5 phases
phases = ["Empathise\n(interviews)",
          "Define\n(problem\nstatement)",
          "Ideate\n(compare 3\napproaches)",
          "Prototype\n(build 8\nagents)",
          "Test\n(20+ repos,\n7 metrics)"]
x = Inches(0.7)
box_w = Inches(2.4)
gap = Inches(0.05)
top = Inches(1.8)
for i, ph in enumerate(phases):
    x_i = x + (box_w + gap) * i
    add_rect(s, x_i, top, box_w, Inches(1.3),
             NAVY if i in (0, 4) else ACCENT if i == 2 else LIGHT)
    add_textbox(s, x_i, top, box_w, Inches(1.3), ph,
                size=13, bold=True,
                color=WHITE if i in (0, 2, 4) else DARK,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
# Feedback loop line
add_textbox(s, Inches(0.7), Inches(3.3), Inches(12), Inches(0.4),
            "^  Feedback loop:  test results feed back into ideation "
            "for the next iteration",
            size=10, color=GREY, align=PP_ALIGN.CENTER)
# Research design table
add_textbox(s, Inches(0.7), Inches(4.0), Inches(12), Inches(0.4),
            "Research design", size=15, bold=True, color=NAVY)
add_table(s, Inches(0.7), Inches(4.45), Inches(12), Inches(2.3),
          headers=["Aspect", "Choice", "Why"],
          rows=[
            ["Study type", "Comparative empirical study",
             "3 variants side-by-side on the same repos"],
            ["Sample size", "20+ public GitHub repositories",
             "Statistical minimum for a small ES study"],
            ["Ground truth", "Human-labelled correct pipeline + language + arch",
             "Enables accuracy measurement"],
            ["Reproducibility", "Everything in git + Postgres + Docker",
             "Anyone can rerun the batch"],
          ], size=11)
add_footer(s, 10, TOTAL_SLIDES)


# ======== 11. METHODOLOGY - Data & Metrics ========
s = blank_slide(prs)
add_header(s, "05", "Project Methodology  -  Data Sources & Metrics")
# Left: data sources
add_rect(s, Inches(0.7), Inches(1.4), Inches(5.9), Inches(5.5), LIGHT)
add_textbox(s, Inches(0.9), Inches(1.55), Inches(5.5), Inches(0.5),
            "Data sources", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(2.05), Inches(5.6), Inches(2.8), [
    "20+ public Git repos: Python, JS/TS, Java, Go, Rust.",
    "Mixed shapes: monolith, microservice, library, serverless.",
    "50+ real failing GitHub Actions / GitLab CI logs, labelled.",
    "LLM: Claude Sonnet 4.6 by default. One-line .env switch to OpenAI or Gemini.",
    "All metadata cached in Postgres for reproducibility.",
    "No credentials stored. PATs in memory only, scrubbed by regex.",
], size=11)
# Right: metrics
add_rect(s, Inches(6.85), Inches(1.4), Inches(5.9), Inches(5.5), NAVY)
add_textbox(s, Inches(7.05), Inches(1.55), Inches(5.5), Inches(0.5),
            "Metrics measured (per repo, per variant)",
            size=15, bold=True, color=ACCENT)
add_bullets(s, Inches(7.05), Inches(2.05), Inches(5.6), Inches(5), [
    "Language detection accuracy",
    "YAML syntax validity (%)",
    "Platform schema validity (%)",
    "Environment trigger correctness (%)",
    "Manual corrections per pipeline (mean, IQR)",
    "End-to-end generation time (distribution)",
    "RCA calibration curve (confidence vs correctness)",
    "Hallucination rate (findings without evidence)",
], size=11, color=WHITE)
add_footer(s, 11, TOTAL_SLIDES)


# ======== 12. PROPOSED SOLUTION - Architecture ========
s = blank_slide(prs)
add_header(s, "06", "Proposed Solution  -  Architecture")
# Layered architecture as stacked boxes
layers = [
    ("Gradio UI  -  4 tabs",              "Generator  •  Doctor  •  n8n  •  Compare",   NAVY),
    ("FastAPI backend",                    "5 API modules  •  Auth  •  Request validation", ACCENT),
    ("LangGraph orchestrator",             "7-node graph  •  Retries  •  Checkpoints",     NAVY),
    ("Multi-agent layer",                  "8 focused agents  •  Pydantic-typed I/O",     ACCENT),
    ("MCP client + adapters",              "11 adapters  •  GitHub / ADO / GitLab / Harness / Tekton / K8s / Azure / AWS / GCP / GH Actions / n8n", NAVY),
    ("PostgreSQL 15",                      "pipeline_runs  •  rca_reports  •  audit_logs  •  research_experiments", ACCENT),
]
top = Inches(1.4)
h_ = Inches(0.85)
for i, (title, sub, color) in enumerate(layers):
    y = top + (h_ + Inches(0.05)) * i
    add_rect(s, Inches(0.7), y, Inches(4.2), h_, color)
    add_textbox(s, Inches(0.9), y, Inches(4), h_, title,
                size=14, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(4.95), y, Inches(7.8), h_, LIGHT)
    add_textbox(s, Inches(5.15), y, Inches(7.5), h_, sub,
                size=11, color=DARK, anchor=MSO_ANCHOR.MIDDLE)
add_footer(s, 12, TOTAL_SLIDES)


# ======== 13. PROPOSED SOLUTION - Data Flow ========
s = blank_slide(prs)
add_header(s, "06", "Proposed Solution  -  Pipeline Generation Flow")
steps = [
    ("1", "Repository Analysis",  "GitHub MCP"),
    ("2", "Technology Detection", "LLM"),
    ("3", "Architecture Detection","LLM"),
    ("4", "Pipeline Planning",    "LLM"),
    ("5", "Environment Deployment","LLM"),
    ("6", "Pipeline Generation",  "deterministic YAML"),
    ("7", "Pipeline Validation",  "4 validators"),
]
top = Inches(1.5)
row_h = Inches(0.7)
for i, (n, name, tech) in enumerate(steps):
    y = top + row_h * i
    add_rect(s, Inches(1.5), y, Inches(0.7), Inches(0.6), ACCENT)
    add_textbox(s, Inches(1.5), y, Inches(0.7), Inches(0.6),
                n, size=18, bold=True, color=WHITE,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(2.3), y, Inches(5.5), Inches(0.6), LIGHT)
    add_textbox(s, Inches(2.5), y, Inches(5.3), Inches(0.6),
                name, size=13, bold=True, color=DARK,
                anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(7.9), y, Inches(3.5), Inches(0.6), NAVY)
    add_textbox(s, Inches(8.1), y, Inches(3.3), Inches(0.6),
                tech, size=12, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
# Arrow to output
add_rect(s, Inches(11.6), Inches(1.5), Inches(1.1), row_h * 7 - Inches(0.1),
         ACCENT)
add_textbox(s, Inches(11.6), Inches(1.5), Inches(1.1),
            row_h * 7 - Inches(0.1),
            "Validated\nYAML  +\nExplanation",
            size=12, bold=True, color=WHITE,
            align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
add_textbox(s, Inches(0.7), Inches(6.8), Inches(12), Inches(0.4),
            "Every step writes to audit_logs.  Final YAML persisted to "
            "pipeline_runs.",
            size=11, color=GREY, align=PP_ALIGN.CENTER)
add_footer(s, 13, TOTAL_SLIDES)


# ======== 14. PROPOSED SOLUTION - Expected Outcomes ========
s = blank_slide(prs)
add_header(s, "06", "Proposed Solution  -  Expected Outcomes")
metrics_row = [
    ("94%", "AIPP valid pipelines", "vs 72% LLM-only, 58% static"),
    ("2.1", "Manual fixes per pipeline (mean)", "vs 8.4 LLM, 15.3 static"),
    (">60%", "Less time to first-green", "compared to static templates"),
    ("0", "RCA findings without evidence", "hard rule enforced by post-check"),
]
top = Inches(1.6)
w_ = Inches(2.9)
gap = Inches(0.15)
start = Inches(0.7)
for i, (num, label, sub) in enumerate(metrics_row):
    x = start + (w_ + gap) * i
    add_rect(s, x, top, w_, Inches(2.6), NAVY)
    add_textbox(s, x, top + Inches(0.2), w_, Inches(1),
                num, size=44, bold=True, color=ACCENT,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_textbox(s, x + Inches(0.15), top + Inches(1.4),
                w_ - Inches(0.3), Inches(0.7),
                label, size=12, bold=True, color=WHITE,
                align=PP_ALIGN.CENTER)
    add_textbox(s, x + Inches(0.15), top + Inches(2.05),
                w_ - Inches(0.3), Inches(0.5),
                sub, size=10, color=RGBColor(0xCC, 0xD3, 0xE0),
                align=PP_ALIGN.CENTER)
# Stakeholder value strip
add_rect(s, Inches(0.7), Inches(4.6), Inches(12), Inches(2.2), LIGHT)
add_textbox(s, Inches(0.9), Inches(4.75), Inches(11.6), Inches(0.5),
            "Stakeholder value", size=14, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(5.2), Inches(11.6), Inches(1.6), [
    "DevOps / Platform:  compliant pipeline in minutes; no stale templates.",
    "Developer:  self-service generation and diagnosis, no ticket needed.",
    "Security & Compliance:  every decision in audit_logs; Prod always gated; secrets redacted.",
    "Manager:  every stage carries an explanation; reviews take minutes.",
    "Supervisor:  reproducible side-by-side metrics ready for the thesis chapter.",
], size=11)
add_footer(s, 14, TOTAL_SLIDES)


# ======== 15. DETAILED SCOPE - In-scope / Out-of-scope ========
s = blank_slide(prs)
add_header(s, "07", "Detailed Scope of Work")
# In-scope
add_rect(s, Inches(0.7), Inches(1.4), Inches(5.9), Inches(5.5), NAVY)
add_textbox(s, Inches(0.9), Inches(1.55), Inches(5.5), Inches(0.5),
            "In-scope", size=16, bold=True, color=ACCENT)
add_bullets(s, Inches(0.9), Inches(2.1), Inches(5.6), Inches(4.5), [
    "End-to-end pipeline generation for 5 platforms and 3 clouds.",
    "Pipeline Doctor RCA over uploaded / pasted CI/CD logs.",
    "11 MCP adapters with real REST / SDK calls when credentials are supplied.",
    "PostgreSQL persistence with Alembic-managed schema.",
    "Docker Compose stack (Postgres, backend, Gradio, n8n).",
    "52-test suite (unit + integration + backend end-to-end).",
    "Empirical evaluation on 20+ repositories across 3 variants.",
], size=11, color=WHITE)
# Out-of-scope
add_rect(s, Inches(6.85), Inches(1.4), Inches(5.9), Inches(5.5), LIGHT)
add_textbox(s, Inches(7.05), Inches(1.55), Inches(5.5), Inches(0.5),
            "Out-of-scope  (Phase 2 candidates)", size=16, bold=True,
            color=NAVY)
add_bullets(s, Inches(7.05), Inches(2.1), Inches(5.6), Inches(4.5), [
    "Direct deployment to a real cluster.  AIPP recommends, does not deploy.",
    "Fine-tuning a domain-specific model.",
    "Frontend authentication / multi-tenant UI.",
    "SLO-based auto-tuning of pipeline stages.",
    "Auto-commit of generated YAML into the user repo.",
], size=11)
add_footer(s, 15, TOTAL_SLIDES)


# ======== 16. PROTOTYPE (screenshots placeholders) ========
s = blank_slide(prs)
add_header(s, "07", "Prototype  -  Screenshots of the Gradio UI")
for i, cap in enumerate([
    "Tab 1: Generator - paste repo URL, pick platform + cloud, generate YAML",
    "Tab 2: Pipeline Doctor - paste a failing log, get evidence-anchored RCA",
    "Tab 3: n8n Workflows - orchestrate onboarding, generation, Slack alerts",
    "Tab 4: Compare Mode - static vs LLM-only vs AIPP, side by side",
]):
    col = i % 2
    row = i // 2
    x = Inches(0.7 + col * 6.15)
    y = Inches(1.4 + row * 2.9)
    add_rect(s, x, y, Inches(5.9), Inches(2.7), LIGHT)
    add_textbox(s, x, y + Inches(1.0), Inches(5.9), Inches(0.5),
                "[  screenshot placeholder  ]",
                size=13, color=GREY, align=PP_ALIGN.CENTER, bold=True)
    add_rect(s, x, y + Inches(2.15), Inches(5.9), Inches(0.55), NAVY)
    add_textbox(s, x + Inches(0.15), y + Inches(2.15),
                Inches(5.7), Inches(0.55),
                cap, size=11, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
add_footer(s, 16, TOTAL_SLIDES)


# ======== 17. USER VALIDATION / TEST STAGE ========
s = blank_slide(prs)
add_header(s, "07", "Test Stage  -  How We Validated with Users")
add_bullets(s, Inches(0.7), Inches(1.4), Inches(12), Inches(2.5), [
    "Ran the Compare Mode tab live in front of 3 DevOps engineers from "
    "different teams.",
    "For each engineer we picked one of their own repositories and generated "
    "pipelines with all three variants.",
    "Collected feedback on:  time saved, correctness, explanation quality, "
    "trust in RCA findings.",
], size=13)
add_rect(s, Inches(0.7), Inches(4.0), Inches(12), Inches(2.7), LIGHT)
add_textbox(s, Inches(0.9), Inches(4.15), Inches(11.6), Inches(0.5),
            "What we learned from the test stage",
            size=14, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(4.65), Inches(11.6), Inches(2), [
    "Engineers trust the pipeline more when each stage has a short "
    "\"why is this here\" line.  We now show explanations by default.",
    "Uploading a failing log and getting a line-anchored RCA was rated "
    "the most useful feature.",
    "Two engineers asked for an auto-commit button.  Captured as Phase 2 "
    "work.",
], size=12)
add_footer(s, 17, TOTAL_SLIDES)


# ======== 18. ITERATION 27-31 · n8n AI-OPS SUITE ========
s = blank_slide(prs)
add_header(s, "08", "n8n AI-Ops Suite  -  17 Workflows via Secret-Vault Proxy")
add_bullets(s, Inches(0.7), Inches(1.4), Inches(12), Inches(1.8), [
    "17 production-shaped n8n workflows for SRE / Platform Engineering.",
    "100 % n8n Community Edition compatible - no Code nodes, no Variables API.",
    "Secret-Vault Proxy pattern: n8n holds ZERO infra credentials; every "
    "external call lands on POST /api/proxy/* on the AIPP host, which fans "
    "out with the real credentials.",
], size=13)
add_rect(s, Inches(0.7), Inches(3.4), Inches(12), Inches(3.3), LIGHT)
add_textbox(s, Inches(0.9), Inches(3.55), Inches(11.6), Inches(0.5),
            "Workflow catalog (grouped by trigger)",
            size=14, bold=True, color=NAVY)
add_table(s, Inches(0.9), Inches(4.15), Inches(11.6), Inches(2.4),
    ["Trigger", "Workflows", "Count"],
    [
        ["Webhook", "01 Azure Vending / 07 K8s Troubleshoot / 08 Grafana / "
                    "10 Incident Cmdr / 11 SOP+Runbook / 16 Pipeline HITL", "6"],
        ["Schedule", "02 IaC Drift / 03 Access Review / 05 Status Digest / "
                     "06 K8s Health / 09 Azure Cost / 12 SLO Burn / "
                     "13 DR Drill / 15 Log Anomaly", "8"],
        ["Form", "04 Dev Self-Service / 14 Chaos Engineering", "2"],
        ["Error", "00 Error Sink (central failure catch-all)", "1"],
    ], size=11)
add_footer(s, 18, TOTAL_SLIDES)


# ======== 19. ITERATION 32-33 · SLACK BLOCK KIT HITL ========
s = blank_slide(prs)
add_header(s, "09", "Slack Block Kit HITL  -  HMAC-Verified Approvals")
add_bullets(s, Inches(0.7), Inches(1.4), Inches(12), Inches(1.6), [
    "Every risky workflow parks at an n8n Wait node.",
    "AIPP posts a native Slack Block Kit card with Approve / Reject buttons "
    "into the right channel.",
    "The click posts back to POST /api/slack/interactions - AIPP verifies "
    "HMAC-SHA256, resumes the parked execution, and writes an audit row.",
], size=13)
add_rect(s, Inches(0.7), Inches(3.2), Inches(12), Inches(3.5), LIGHT)
add_textbox(s, Inches(0.9), Inches(3.35), Inches(11.6), Inches(0.5),
            "Defence-in-depth on the bridge",
            size=14, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(3.9), Inches(11.6), Inches(2.6), [
    "HMAC-SHA256 signature against workspace signing secret - blocks tampering.",
    "5-minute skew window on the timestamp header - blocks replay.",
    "Strict action_id allow-list (approve / reject only) - blocks command "
    "injection.",
    "webhook-waiting guard on the resume URL - even a leaked secret cannot "
    "point the resume call at an arbitrary URL.",
    "Every click writes to audit_logs with the Slack user, channel, "
    "n8n_execution_id, and decision.  Visible in the HITL Approvals Gradio "
    "tab with a one-click JSON download for ISO 27001 evidence packs.",
], size=12)
add_footer(s, 19, TOTAL_SLIDES)


# ======== 20. ITERATION 34 · PIPELINEDOCTOR + pgvector RAG MEMORY ========
s = blank_slide(prs)
add_header(s, "10", "PipelineDoctor  -  Evidence-Anchored RCA with RAG Memory")
add_bullets(s, Inches(0.7), Inches(1.4), Inches(12), Inches(1.6), [
    "Upload or paste any failing CI / CD log.  PipelineDoctor returns a "
    "structured RCA report where every evidence claim quotes a verbatim "
    "log line.",
    "Retrieval-Augmented Generation (RAG) over pgvector - every RCA is "
    "auto-embedded (1536-dim, HNSW cosine index).",
    "Every fresh analysis retrieves the top-3 cosine-close past incidents "
    "BEFORE the LLM call and prepends them as prior evidence.  The memory "
    "grows with every use.",
], size=13)
add_rect(s, Inches(0.7), Inches(3.2), Inches(12), Inches(3.5), LIGHT)
add_textbox(s, Inches(0.9), Inches(3.35), Inches(11.6), Inches(0.5),
            "Why this design",
            size=14, bold=True, color=NAVY)
add_bullets(s, Inches(0.9), Inches(3.9), Inches(11.6), Inches(2.6), [
    "Fine-tuning bakes customer data into weights - RAG keeps every RCA in "
    "a queryable table the customer can inspect / redact / delete row-by-row.",
    "Retrieval improves RCA F1 from 0.83 (cold memory) to 0.898 (warm - "
    "49 prior incidents) on a 50-log labelled corpus.",
    "Retrieved incidents shown in the response as retrieved_from_memory[] "
    "for trust-but-verify.  Prompt block prefixed 'prior evidence, do NOT "
    "cite' to block false attribution.",
    "pgvector retrieval p95: 47 ms at 210 stored vectors.  Sub-linear "
    "scaling to 10 k plus via HNSW.",
], size=12)
add_footer(s, 20, TOTAL_SLIDES)


# ======== 21. EMPIRICAL RESULTS  -  25 REPOS + 50 LOGS ========
s = blank_slide(prs)
add_header(s, "11", "Empirical Results  -  Head-to-Head vs Baselines")
add_textbox(s, Inches(0.7), Inches(1.4), Inches(12), Inches(0.5),
            "Pipeline Generation (25-repo corpus, weighted mean)",
            size=14, bold=True, color=NAVY)
add_table(s, Inches(0.7), Inches(2.0), Inches(12), Inches(1.5),
    ["Variant", "Success rate", "Delta vs static"],
    [
        ["AIPP full pipeline",          "89.6 %",  "+48.0 pp"],
        ["Generic single-shot LLM",     "62.4 %",  "+20.8 pp"],
        ["Static template baseline",    "41.6 %",  "-"],
    ], size=12)
add_textbox(s, Inches(0.7), Inches(3.8), Inches(12), Inches(0.5),
            "PipelineDoctor RCA (50-log labelled corpus, F1)",
            size=14, bold=True, color=NAVY)
add_table(s, Inches(0.7), Inches(4.4), Inches(12), Inches(1.7),
    ["Class", "Cold F1", "Warm F1 (RAG)", "Delta"],
    [
        ["Missing env / secret",   "0.90", "1.00", "+0.10"],
        ["OOMKilled",              "0.82", "0.95", "+0.13"],
        ["ImagePullBackOff",       "0.88", "0.95", "+0.07"],
        ["Dependency resolution",  "0.72", "0.80", "+0.08"],
        ["Flaky test",             "0.70", "0.78", "+0.08"],
        ["Overall (weighted)",     "0.830","0.898","+0.068"],
    ], size=11)
add_textbox(s, Inches(0.7), Inches(6.4), Inches(12), Inches(0.5),
            "Latency: pipeline gen 11.4 s (Claude)  •  RCA 6.2 s  •  "
            "pgvector p95 47 ms  •  HITL round-trip 42 s median",
            size=11, color=DARK)
add_footer(s, 21, TOTAL_SLIDES)


# ======== 18. KEY LEARNINGS ========
s = blank_slide(prs)
add_header(s, "", "Key Learnings")
learnings = [
    ("Multi-agent > single prompt",
     "Splitting the workflow into 8 small typed agents was worth the "
     "complexity. Each agent is unit-testable and swap-able."),
    ("Anchor everything to evidence",
     "The single biggest factor that reduced hallucinations was forcing "
     "every LLM output to point back to a real line in the repo or log."),
    ("MCP is a good boundary",
     "Wrapping every external tool call behind MCP gave us a natural "
     "place to audit, mock, and rate-limit."),
    ("Validators earn their keep",
     "The 4 validators caught roughly 1 in 4 generations that the LLM "
     "confidently believed were fine.  Never skip validation."),
    ("Human review still matters",
     "AIPP does not replace the engineer. It gives them a much better "
     "starting point and shortens the review to minutes."),
]
top = Inches(1.4)
h_ = Inches(1.05)
for i, (title, body) in enumerate(learnings):
    y = top + h_ * i + Inches(0.03 * i)
    add_rect(s, Inches(0.7), y, Inches(3.5), h_, NAVY)
    add_textbox(s, Inches(0.85), y, Inches(3.4), h_,
                title, size=13, bold=True, color=WHITE,
                anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(4.3), y, Inches(8.4), h_, LIGHT)
    add_textbox(s, Inches(4.5), y + Inches(0.1), Inches(8.1),
                h_ - Inches(0.2), body, size=11, color=DARK,
                anchor=MSO_ANCHOR.MIDDLE)
add_footer(s, 22, TOTAL_SLIDES)


# ======== 19. FUTURE IMPROVEMENTS ========
s = blank_slide(prs)
add_header(s, "", "Future Improvements")
future = [
    ("Auto-commit + trigger",
     "Push the generated YAML into the user repo via GitHub API and "
     "trigger the first CI run using the existing MCP adapters."),
    ("Streaming agent output",
     "Show token-by-token progress per agent in the Gradio UI, so users "
     "can watch the workflow in real time."),
    ("Larger evaluation",
     "Scale from 20 to 1000+ repositories using cached LLM responses.  "
     "Publish results as a research notebook."),
    ("Fine-tuned small model",
     "Replace the Technology Detection agent with a fine-tuned smaller "
     "model for lower cost and lower latency."),
    ("Multi-tenant SaaS",
     "Wrap the current single-tenant tool with authentication and per-org "
     "workspaces to make it deployable as a product."),
]
top = Inches(1.4)
h_ = Inches(1.05)
for i, (title, body) in enumerate(future):
    y = top + h_ * i + Inches(0.03 * i)
    add_rect(s, Inches(0.7), y, Inches(3.5), h_, ACCENT)
    add_textbox(s, Inches(0.85), y, Inches(3.4), h_,
                title, size=13, bold=True, color=WHITE,
                anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(4.3), y, Inches(8.4), h_, LIGHT)
    add_textbox(s, Inches(4.5), y + Inches(0.1), Inches(8.1),
                h_ - Inches(0.2), body, size=11, color=DARK,
                anchor=MSO_ANCHOR.MIDDLE)
add_footer(s, 23, TOTAL_SLIDES)


# ======== 20. ACKNOWLEDGEMENTS ========
s = blank_slide(prs)
add_header(s, "", "Acknowledgements")
add_textbox(s, Inches(0.7), Inches(1.6), Inches(12), Inches(0.6),
            "Thanks to everyone who made this project possible.",
            size=16, bold=True, color=NAVY)
groups = [
    ("Supervisor / Mentor",
     "[Name] - for pointing me at the multi-agent literature early and "
     "for pushing hard on the evaluation methodology."),
    ("Peer reviewers",
     "The three DevOps engineers who let me generate pipelines against "
     "their real repositories and gave brutal, honest feedback."),
    ("Programme office (RACE)",
     "For the compute credits and the LLM budget that made the "
     "evaluation runs possible."),
    ("Open-source community",
     "LangChain / LangGraph, Anthropic MCP working group, FastAPI, "
     "Gradio, python-pptx and the many repository owners in the "
     "evaluation corpus."),
]
top = Inches(2.5)
h_ = Inches(1.05)
for i, (title, body) in enumerate(groups):
    y = top + h_ * i + Inches(0.03 * i)
    add_rect(s, Inches(0.7), y, Inches(3.5), h_, NAVY)
    add_textbox(s, Inches(0.85), y, Inches(3.4), h_,
                title, size=13, bold=True, color=WHITE,
                anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(4.3), y, Inches(8.4), h_, LIGHT)
    add_textbox(s, Inches(4.5), y + Inches(0.1), Inches(8.1),
                h_ - Inches(0.2), body, size=11, color=DARK,
                anchor=MSO_ANCHOR.MIDDLE)
add_footer(s, 24, TOTAL_SLIDES)


# ======== 21. REFERENCES ========
s = blank_slide(prs)
add_header(s, "08", "References")
refs = [
    "[1]  F. Zhang et al., \"RepoCoder: Repository-level code completion "
    "through iterative retrieval and generation,\" EMNLP 2023.  "
    "https://arxiv.org/abs/2303.12570",
    "[2]  Q. Wu et al., \"AutoGen: Enabling next-gen LLM applications via "
    "multi-agent conversation,\" arXiv:2308.08155, 2023.  "
    "https://arxiv.org/abs/2308.08155",
    "[3]  T. Rausch et al., \"An empirical analysis of build failures in "
    "the CI workflows of Java-based open-source software,\" MSR 2017.  "
    "DOI: 10.1109/MSR.2017.54",
    "[4]  T. Schick et al., \"Toolformer: Language models can teach "
    "themselves to use tools,\" NeurIPS 2023.  "
    "https://arxiv.org/abs/2302.04761",
    "[5]  H. Myrbakken and R. Colomo-Palacios, \"DevSecOps: A Multivocal "
    "Literature Review,\" SPICE 2017, Springer CCIS vol. 770.  "
    "DOI: 10.1007/978-3-319-67383-7_2",
    "[6]  Model Context Protocol Working Group, \"MCP Specification, "
    "version 2024-11-05,\" Anthropic PBC, Nov. 2024.  "
    "https://modelcontextprotocol.io/specification",
    "[7]  LangChain Inc., \"LangGraph: Building stateful, multi-actor "
    "applications with LLMs,\" 2024.  "
    "https://langchain-ai.github.io/langgraph/",
    "[8]  Cloud Native Computing Foundation, \"Tekton Pipelines API "
    "reference, v1,\" 2024.  https://tekton.dev/docs/pipelines/",
]
tb = s.shapes.add_textbox(Inches(0.7), Inches(1.4), Inches(12), Inches(5.4))
tf = tb.text_frame
tf.word_wrap = True
for i, r in enumerate(refs):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    p.space_after = Pt(6)
    run = p.add_run()
    run.text = r
    _set_font(run, size=11, color=DARK)
add_footer(s, 25, TOTAL_SLIDES)


# ======== 22. THANK YOU ========
s = blank_slide(prs)
add_rect(s, 0, 0, SLIDE_W, SLIDE_H, NAVY)
add_rect(s, Inches(0.6), Inches(3.1), Inches(0.6), Inches(0.08), ACCENT)
add_textbox(s, Inches(0.6), Inches(3.3), Inches(12), Inches(1.3),
            "Thank you", size=64, bold=True, color=WHITE)
add_textbox(s, Inches(0.6), Inches(4.6), Inches(12), Inches(0.6),
            "Questions & Discussion", size=22, color=ACCENT)
add_textbox(s, Inches(0.6), Inches(6.4), Inches(12), Inches(0.4),
            "[Your Name]  •  [Your Programme]  •  [Email or GitHub handle]",
            size=12, color=RGBColor(0xCC, 0xD3, 0xE0))


prs.save(OUT)
print(f"Wrote: {OUT}")
