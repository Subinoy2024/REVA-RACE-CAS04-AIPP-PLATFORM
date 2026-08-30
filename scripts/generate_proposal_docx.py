"""Generate the Capstone Project Proposal DOCX (short, plain-English version).

Run from repo root:
    python3 docs/generate_proposal_docx.py

Output: docs/AIPP_Capstone_Proposal.docx
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt, RGBColor

OUT = Path(__file__).resolve().parent / "AIPP_Capstone_Proposal.docx"

TITLE = ("Design and Implementation of an Automated Multi-Cloud CI/CD "
         "Pipeline Generation and Deployment Orchestration Platform for DevSecOps")


# ---------- helpers ----------
def _shade(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def h(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    return p


def para(doc, text, *, bold=False, italic=False, size=11, align=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def bullet(doc, text):
    doc.add_paragraph(text, style="List Bullet")


def number(doc, text):
    doc.add_paragraph(text, style="List Number")


def table(doc, headers, rows, *, first_col_bold=False):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, hd in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(hd)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade(c, "1F3A5F")
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            c = t.rows[ri].cells[ci]
            c.text = ""
            r = c.paragraphs[0].add_run(str(val))
            r.font.size = Pt(10)
            if first_col_bold and ci == 0:
                r.bold = True
            c.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    return t


def mono(doc, text: str):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = "Consolas"
    r.font.size = Pt(8.5)
    p.paragraph_format.left_indent = Cm(0.4)
    p.paragraph_format.space_after = Pt(6)


# ---------- build ----------
doc = Document()
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(11)
for s in doc.sections:
    s.left_margin = Cm(2)
    s.right_margin = Cm(2)
    s.top_margin = Cm(2)
    s.bottom_margin = Cm(2)


# ==== TITLE PAGE ====
para(doc, "Capstone Project Proposal", bold=True, size=22, align="center")
para(doc, "", size=8)
para(doc, TITLE, bold=True, size=14, align="center")
para(doc, "", size=8)
para(doc, "Prepared by:  [Your Name]", align="center")
para(doc, "Programme:    [Your Programme]", align="center")
para(doc, "Supervisor:   [Proposed Mentor Name]", align="center")
para(doc, "Date:         [DD-MM-YYYY]", align="center")
doc.add_page_break()


# ==== 1. PROJECT NAME ====
h(doc, "1. Project Name", 1)
para(doc, TITLE, bold=True)


# ==== 2. BACKGROUND ====
h(doc, "2. Background Information", 1)
para(doc,
     "Every project team ships code through a CI/CD pipeline that builds, tests, scans and deploys "
     "the app across Development, QA, Staging and Production, mostly on Azure, AWS or GCP. In real "
     "work, someone writes this YAML by hand for each service, and also for each CI/CD tool (Azure "
     "DevOps, GitHub Actions, GitLab CI, Harness, Tekton). This takes days per service. It also "
     "creates inconsistency across teams. As you know, it is one of the biggest reasons for release "
     "delays. We also have to keep checking with the developer for small confirmations while "
     "creating the yml file, like which branch to build, which environment to deploy to, is there "
     "a Dockerfile or not. Multiply this across 20 services and it becomes a full-time job.")
para(doc,
     "When the pipeline fails, engineers spend a lot of time reading long vendor logs just to find "
     "where it broke. Existing tools don't clearly separate confirmed evidence from guesses. And "
     "generic LLM helpers often invent error messages that are not even in the log, which makes "
     "the review harder, not easier.")
para(doc,
     "My project AIPP is built to solve both of these problems together. It reads a Git repository, "
     "understands the technology stack, and generates a working CI/CD pipeline for the tool and "
     "cloud you selected. It also has a Pipeline Doctor feature that reads a failing pipeline log "
     "and returns a root cause report where every finding is tied back to a real line in the log.")


# ==== 3. LITERATURE REVIEW ====
h(doc, "3. Literature Review", 1)
refs_short = [
    ("[1] Repository-level context in LLM code generation",
     "Zhang and team [1] built RepoCoder. They showed that if you feed the LLM relevant code from "
     "the repository itself, code completion gets much better on real projects. I use the same "
     "idea, but at pipeline level. The Repository Analysis agent first collects the file tree, "
     "the dependency files, the Dockerfiles and any Kubernetes or Helm files, before we start "
     "generating anything."),
    ("[2] Multi-agent orchestration for software engineering",
     "Wu and team [2] proposed AutoGen. Their point is simple. If you split one engineering task "
     "across several focused LLM agents, you get better accuracy and better traceability than "
     "using one big prompt. AIPP follows the same pattern. We have eight small agents each doing "
     "one job, and they talk to each other through LangGraph."),
    ("[3] CI/CD failure patterns",
     "Rausch and team [3] looked at 3.7 million Travis CI builds and grouped the failures into "
     "common classes (dependency errors, flaky tests, image pull failures, missing environment "
     "variables). So we took this list and made it a hard rule inside Pipeline Doctor. Every "
     "guess the LLM makes must point to a real log line, no invention."),
    ("[4] Tool-augmented LLMs reduce hallucination",
     "Schick and team [4] worked on Toolformer. They showed that when an LLM is allowed to call "
     "real tools instead of just guessing, it makes fewer factual mistakes. So AIPP does the "
     "same thing through the Model Context Protocol. Agents cannot answer from imagination. "
     "They must call the real GitHub API, the real n8n, the real cloud SDK, and use the actual "
     "data that comes back."),
    ("[5] DevSecOps practices review",
     "Myrbakken and Colomo-Palacios [5] surveyed DevSecOps papers and found three principles "
     "that keep coming up: automation, continuous monitoring and immutable audit trails. AIPP "
     "applies all three. Every agent decision and every tool call gets written into a Postgres "
     "audit table. And we do not allow any pipeline to reach Production without a manual "
     "approval step."),
]
for head, body in refs_short:
    p = doc.add_paragraph()
    r = p.add_run(head + ". ")
    r.bold = True
    p.add_run(body)


# ==== 4. STATEMENT OF PROBLEM ====
h(doc, "4. Statement of the Problem", 1)
para(doc,
     "Writing production-grade CI/CD pipelines by hand is slow and inconsistent. As the number of "
     "services grows, keeping them in sync becomes harder. Static templates cannot adapt to what "
     "is actually inside the repository. And when we try to use a single LLM prompt, the YAML "
     "often fails validation, or it invents commands that don't exist in that CI/CD tool.")
para(doc,
     "Diagnosis is equally painful. When something breaks in the pipeline, the on-call engineer "
     "scrolls through hundreds of log lines just to find the failed stage. So AIPP tries to solve "
     "two problems together. It generates validated pipelines automatically for the 5 CI/CD tools "
     "and 3 clouds. And it diagnoses failures with evidence, not guesses.")


# ==== 5. OBJECTIVES ====
h(doc, "5. Objectives", 1)
objs = [
    ("Objective 1",
     "Build a workflow using several small agents that reads a Git repo and generates ready-to-"
     "deploy CI/CD YAML for the 5 tools (Azure DevOps, GitHub Actions, GitLab CI, Harness, "
     "Tekton). Every stage in the output should have a short line saying why it is there."),
    ("Objective 2",
     "Build the environment deployment engine so it can produce Dev, QA, Staging and Production "
     "stages with the right triggers, approval gates, health checks and rollback settings for "
     "the target cloud (Azure, AWS, GCP)."),
    ("Objective 3",
     "Build a plug-in MCP integration layer with adapters for GitHub, GitHub Actions, Azure "
     "DevOps, GitLab, Harness, Tekton, Kubernetes, Azure, AWS, GCP and n8n. The goal is that "
     "adding a new tool later should not need any change inside agent code."),
    ("Objective 4",
     "Compare AIPP against two baselines (static templates and single-prompt LLM) on 20+ public "
     "repositories. Measure pipeline validity, generation time, manual corrections and "
     "hallucination rate. Also add the Pipeline Doctor feature for evidence-based RCA over "
     "failing logs."),
]
for name, body in objs:
    p = doc.add_paragraph()
    r = p.add_run(name + ": ")
    r.bold = True
    p.add_run(body)


# ==== 6. METHODOLOGY ====
h(doc, "6. Methodology", 1)

h(doc, "6.1 Data sources", 2)
bullet(doc, "20+ public Git repositories covering Python, JavaScript/TypeScript, Java, Go and Rust. "
            "Mix of monoliths, microservices, libraries and serverless. Some with Dockerfile, some "
            "without. Some with existing CI/CD, some without.")
bullet(doc, "50+ real failing CI/CD logs from public GitHub Actions and GitLab CI runs, each one "
            "labelled with the actual root cause and the fix that worked.")
bullet(doc, "LLM back-end: Claude Sonnet 4.6 by default. Through a universal key setup you can also "
            "switch to OpenAI GPT or Google Gemini by changing one line in the .env file.")

h(doc, "6.2 Implementation plan", 2)
table(doc,
      headers=["Phase", "Deliverable", "Duration"],
      rows=[
          ["P1", "Project skeleton, PostgreSQL schema, FastAPI base, Docker Compose stack", "Week 1"],
          ["P2", "GitHub MCP adapter + Repository, Technology, Architecture agents", "Weeks 2-3"],
          ["P3", "Pipeline planner + 5 CI/CD YAML generators", "Weeks 4-6"],
          ["P4", "Environment engine, validators, LangGraph orchestrator", "Weeks 7-8"],
          ["P5", "PipelineDoctor RCA feature", "Week 9"],
          ["P6", "Gradio UI (4 tabs), n8n integration", "Week 10"],
          ["P7", "Remaining MCP adapters (ADO, GitLab, Harness, Tekton, K8s, Azure, AWS, GCP)",
                 "Weeks 11-12"],
          ["P8", "Evaluation batch runs, metrics, thesis write-up", "Weeks 13-16"],
      ],
      first_col_bold=True)

h(doc, "6.3 Analysis", 2)
para(doc,
     "For every repository we run all three variants side by side: static template, single-prompt "
     "LLM, and full AIPP. Metrics get written into the research_experiments table. Then we use "
     "pandas / Jupyter to compare validity rates, generation time, manual corrections and "
     "hallucination rate.")


# ==== 7. PROPOSED SOLUTION / EXPECTED RESULTS ====
h(doc, "7. Proposed Solution / Expected Results", 1)
table(doc,
      headers=["Stakeholder", "Benefit"],
      rows=[
          ["DevOps / Platform engineer",
           "Gets a compliant pipeline in minutes instead of days; no copy-paste from stale templates."],
          ["Application developer",
           "Focuses on code; pipeline generation and log diagnosis are self-service."],
          ["Security / compliance",
           "Every agent decision and tool call is logged; Production always requires an approval gate."],
          ["Engineering manager",
           "Reviews are fast because every stage carries an explanation."],
          ["Academic supervisor",
           "Reproducible side-by-side metrics comparing static, LLM-only and AIPP variants."],
      ],
      first_col_bold=True)
para(doc, "Expected outcomes:", bold=True)
bullet(doc, "Much fewer manual pipeline corrections compared with static templates.")
bullet(doc, "Higher YAML and platform-schema validity than a single-prompt LLM baseline.")
bullet(doc, "Root cause reports that quote real log lines and cut down the time spent on diagnosis.")


# ==== 8. DETAILED SCOPE OF WORK ====
h(doc, "8. Detailed Scope of Work", 1)

h(doc, "8.1 High-level architecture", 2)
mono(doc, """                ┌────────────────────────────────┐
                │  User (DevOps / Developer)     │
                └───────────────┬────────────────┘
                                │ HTTPS
                ┌───────────────▼────────────────┐
                │  Gradio UI  -  4 tabs          │
                │  Generator · Doctor · n8n ·    │
                │  Compare Mode                  │
                └───────────────┬────────────────┘
                                │ REST /api/*
                ┌───────────────▼────────────────┐
                │  FastAPI backend + PostgreSQL  │
                └────┬─────────────────┬─────────┘
                     │                 │
       ┌─────────────▼─────┐   ┌───────▼─────────┐
       │ LangGraph         │   │ Services /      │
       │ multi-agent       │   │ audit trail     │
       │ workflow (7 nodes)│   └───────┬─────────┘
       └─────────┬─────────┘           │
                 │                     │
                 ▼                     ▼
       ┌─────────────────────┐   ┌───────────────────────┐
       │  MCP client         │   │  PostgreSQL 15        │
       │  (real REST/SDK)    │   │  runs / rca / audit / │
       └────────┬────────────┘   │  research metrics     │
                │                └───────────────────────┘
                ▼
   ┌──────────────────────────────────────┐
   │  MCP adapters (11)                   │
   │  GitHub · ADO · GitLab · Harness ·   │
   │  Tekton · K8s · Azure · AWS · GCP ·  │
   │  GitHub Actions · n8n                │
   └──────────────────────────────────────┘""")

h(doc, "8.2 Pipeline generation flow", 2)
mono(doc, """User submits repo URL + PAT + branch + CI/CD platform + cloud + requirement
                    │
                    ▼
   [1] Repository Analysis Agent   (GitHub MCP)
                    │
                    ▼
   [2] Technology Detection Agent  (LLM)
                    │
                    ▼
   [3] Architecture Detection Agent (LLM)
                    │
                    ▼
   [4] Pipeline Planning Agent      (LLM)
                    │
                    ▼
   [5] Environment Deployment Agent (LLM)
                    │
                    ▼
   [6] Pipeline Generation Agent    (deterministic YAML)
                    │
                    ▼
   [7] Pipeline Validation Agent
                    │
     ┌──────────────┴───────────────┐
     ▼                              ▼
Downloadable YAML       Explanation + validation report
     │
     ▼
Persist to pipeline_runs + audit_logs""")

h(doc, "8.3 In-scope", 2)
for x in [
    "Generation of complete CI/CD pipelines for 5 platforms and 3 clouds",
    "Environment rules for Dev / QA / Staging / Production with approval gates and rollback",
    "PipelineDoctor RCA feature over uploaded/pasted CI/CD logs",
    "MCP adapters for 11 external systems (real REST/SDK calls when credentials are supplied)",
    "PostgreSQL persistence with Alembic migrations",
    "Docker Compose stack (PostgreSQL + backend + Gradio + n8n)",
    "Automated test suite (52 tests currently passing)",
    "Empirical evaluation across three variants on 20+ repositories",
]:
    bullet(doc, x)

h(doc, "8.4 Out-of-scope (Phase-2 candidates)", 2)
for x in [
    "Directly deploying to a real cluster (AIPP recommends but does not execute)",
    "Fine-tuning a domain-specific model",
    "Frontend authentication / multi-tenant UI",
    "SLO-based auto-tuning of pipeline stages",
]:
    bullet(doc, x)


# ==== 9. SUPPORT NEEDED ====
h(doc, "9. Support Needed from Program Office", 1)
table(doc,
      headers=["Item", "Requested"],
      rows=[
          ["Mentor (RACE)",
           "A faculty member with experience in software engineering, DevSecOps, or MLOps."],
          ["External mentor (optional)",
           "Industry practitioner working on Azure DevOps / GitHub Actions / Kubernetes."],
          ["Compute",
           "Small VM (2 vCPU, 4 GB RAM) for the evaluation batch runs."],
          ["LLM budget",
           "Modest LLM inference budget for ~60 evaluation runs (3 variants × 20 repos). "
           "Emergent Universal Key or vendor keys (Anthropic / OpenAI / Gemini)."],
          ["Data",
           "Permission to use publicly-available GitHub repositories and open CI/CD logs."],
          ["Software licences",
           "None. The stack is fully open-source."],
      ],
      first_col_bold=True)


# ==== 10. REFERENCES ====
h(doc, "10. References", 1)
refs = [
    ("[1] F. Zhang, B. Chen, Y. Zhang, J. Keung, J. Liu, D. Zan, Y. Mao, J.-G. Lou, and W. Chen, "
     "\u201cRepoCoder: Repository-level code completion through iterative retrieval and generation,\u201d "
     "in Proc. 2023 Conf. on Empirical Methods in Natural Language Processing (EMNLP), pp. 2471\u20132484, "
     "Dec. 2023. [Online]. Available: https://arxiv.org/abs/2303.12570"),
    ("[2] Q. Wu, G. Bansal, J. Zhang, Y. Wu, S. Zhang, E. Zhu, B. Li, L. Jiang, X. Zhang, and C. Wang, "
     "\u201cAutoGen: Enabling next-gen LLM applications via multi-agent conversation,\u201d "
     "arXiv preprint arXiv:2308.08155, Aug. 2023. [Online]. Available: https://arxiv.org/abs/2308.08155"),
    ("[3] T. Rausch, W. Hummer, P. Leitner, and S. Schulte, \u201cAn empirical analysis of build "
     "failures in the continuous integration workflows of Java-based open-source software,\u201d "
     "in Proc. IEEE/ACM Int. Conf. Mining Software Repositories (MSR), pp. 345\u2013355, May 2017. "
     "DOI: 10.1109/MSR.2017.54. [Online]. Available: "
     "https://dsg.tuwien.ac.at/team/trausch/pub/msr2017-rausch.pdf"),
    ("[4] T. Schick, J. Dwivedi-Yu, R. Dess\u00ec, R. Raileanu, M. Lomeli, L. Zettlemoyer, "
     "N. Cancedda, and T. Scialom, \u201cToolformer: Language models can teach themselves to use "
     "tools,\u201d in Advances in Neural Information Processing Systems (NeurIPS), vol. 36, "
     "Dec. 2023. [Online]. Available: https://arxiv.org/abs/2302.04761"),
    ("[5] H. Myrbakken and R. Colomo-Palacios, \u201cDevSecOps: A Multivocal Literature Review,\u201d "
     "in Software Process Improvement and Capability Determination (SPICE), Communications in Computer "
     "and Information Science, vol. 770, pp. 17\u201329, Springer, 2017. DOI: 10.1007/978-3-319-67383-7_2. "
     "[Online]. Available: https://link.springer.com/chapter/10.1007/978-3-319-67383-7_2"),
    ("[6] Model Context Protocol Working Group, \u201cModel Context Protocol Specification, "
     "version 2024-11-05,\u201d Anthropic PBC, Nov. 2024. [Online]. Available: "
     "https://modelcontextprotocol.io/specification"),
    ("[7] LangChain, Inc., \u201cLangGraph: Building stateful, multi-actor applications with LLMs,\u201d "
     "Documentation, 2024. [Online]. Available: https://langchain-ai.github.io/langgraph/"),
    ("[8] Cloud Native Computing Foundation, \u201cTekton Pipelines API reference, v1,\u201d 2024. "
     "[Online]. Available: https://tekton.dev/docs/pipelines/"),
]
for r in refs:
    p = doc.add_paragraph(r)
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)


# footer
doc.add_paragraph()
p = doc.add_paragraph()
r = p.add_run(f"Prepared by: [Your Name]  |  {'[Your Programme]'}  |  Supervisor: [Name]  |  Date: [DD-MM-YYYY]")
r.italic = True
r.font.size = Pt(9)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER


doc.save(OUT)
print(f"Wrote: {OUT}")
