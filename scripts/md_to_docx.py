"""Convert the AIPP capstone report from Markdown to a formatted DOCX.

Handles:
  * Cover page (centered title + author block)
  * H1/H2/H3 headings mapped to Word's Heading 1/2/3 styles
  * Bullet lists and numbered lists
  * Markdown tables → real Word tables
  * Code blocks in Consolas
  * Horizontal rules → page breaks between chapters
  * Blockquotes as indented italic paragraphs

Run:  python /app/docs/md_to_docx.py
Out:  /app/docs/AIPP_Capstone_Project_Final_Report.docx
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, RGBColor

SRC = Path("/app/docs/AIPP_Capstone_Project_Final_Report.md")
DST = Path("/app/docs/AIPP_Capstone_Project_Final_Report.docx")


def _set_cell_bg(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _add_inline(paragraph, text: str) -> None:
    """Handle inline **bold**, *italic* and `code` spans."""
    # Split on any of the three markers while preserving them.
    pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")
    parts = pattern.split(text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(10)
        else:
            paragraph.add_run(part)


def _add_table(doc: Document, header: list[str], rows: list[list[str]]) -> None:
    tbl = doc.add_table(rows=1 + len(rows), cols=len(header))
    tbl.style = "Light Grid Accent 1"
    for i, h in enumerate(header):
        c = tbl.rows[0].cells[i]
        c.text = ""
        p = c.paragraphs[0]
        run = p.add_run(h.strip())
        run.bold = True
        _set_cell_bg(c, "D9E2F3")
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            if ci < len(tbl.rows[ri + 1].cells):
                target = tbl.rows[ri + 1].cells[ci]
                target.text = ""
                _add_inline(target.paragraphs[0], cell.strip())


def _flush_table(doc, pending_table):
    """Convert a pending list of markdown rows into a Word table."""
    if not pending_table:
        return
    # Row 0 = header; row 1 = separator (---); rows 2+ = data.
    header_row = pending_table[0]
    data_rows = pending_table[2:] if len(pending_table) > 2 else []
    header = [c.strip() for c in _split_row(header_row)]
    rows = [[c.strip() for c in _split_row(r)] for r in data_rows]
    _add_table(doc, header, rows)


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return line.split("|")


def convert(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()

    doc = Document()
    # Global defaults
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    in_code = False
    code_buf: list[str] = []
    pending_table: list[str] = []
    in_html_comment = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Strip HTML comments (we use them as internal notes).
        if "<!--" in line:
            in_html_comment = True
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            i += 1
            continue

        # Fenced code blocks
        if stripped.startswith("```"):
            if in_code:
                # Close block
                p = doc.add_paragraph()
                run = p.add_run("\n".join(code_buf))
                run.font.name = "Consolas"
                run.font.size = Pt(9)
                p.paragraph_format.left_indent = Pt(18)
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # Table detection
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
            pending_table.append(stripped)
            i += 1
            continue
        else:
            if pending_table:
                _flush_table(doc, pending_table)
                pending_table = []

        # Strip surrounding <div align="center"> wrappers
        if stripped.startswith("<div") or stripped.startswith("</div>"):
            i += 1
            continue

        # Horizontal rule → page break
        if stripped == "---":
            doc.add_page_break()
            i += 1
            continue

        # Headings
        if stripped.startswith("# "):
            p = doc.add_heading(stripped[2:].strip(), level=1)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x8A)
            i += 1
            continue
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            p = doc.add_heading(title, level=2)
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x8A)
            i += 1
            continue
        if stripped.startswith("### "):
            p = doc.add_heading(stripped[4:].strip(), level=3)
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x3C, 0x5A, 0xA0)
            i += 1
            continue
        if stripped.startswith("#### "):
            p = doc.add_heading(stripped[5:].strip(), level=4)
            i += 1
            continue

        # Blockquote
        if stripped.startswith("> "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(24)
            run = p.add_run(stripped[2:].strip())
            run.italic = True
            i += 1
            continue

        # Bullet list
        if stripped.startswith("* ") or stripped.startswith("- "):
            content = stripped[2:]
            p = doc.add_paragraph(style="List Bullet")
            _add_inline(p, content)
            i += 1
            continue

        # Numbered list
        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph(style="List Number")
            _add_inline(p, m.group(1))
            i += 1
            continue

        # Blank line
        if not stripped:
            doc.add_paragraph("")
            i += 1
            continue

        # Regular paragraph — collect wrapped lines until a blank / heading /
        # table / list marker breaks it.
        buf = [line]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if (not nxt) or nxt.startswith(("#", "* ", "- ", "> ", "|", "```"))\
               or re.match(r"^\d+\.\s+", nxt) or nxt == "---":
                break
            buf.append(lines[j])
            j += 1
        para_text = " ".join(x.strip() for x in buf if x.strip())
        if para_text:
            p = doc.add_paragraph()
            _add_inline(p, para_text)
        i = j

    # Flush any trailing table.
    if pending_table:
        _flush_table(doc, pending_table)

    doc.save(dst)
    print(f"✓ Wrote {dst} ({dst.stat().st_size:,} bytes)")


if __name__ == "__main__":
    convert(SRC, DST)
