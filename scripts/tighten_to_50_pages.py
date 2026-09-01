"""Calibrate DOCX to precisely ~50 pages by eliminating empty blank paragraphs and tightening table/figure vertical rhythm."""

import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from pathlib import Path

DOC_PATH = Path("/Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/final_deliverable/DEMO_AIPP_Capstone_Project_Final_Report.docx")
DOCS_MIRROR = Path("/Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/docs/AIPP_Capstone_Project_Final_Report.docx")

def set_cell_margins(cell, top=50, bottom=50, left=100, right=100):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def tighten_document(doc_path: Path):
    doc = docx.Document(doc_path)
    
    # 1. Page Margins — 0.9 inch to fit ~50 pages gracefully
    for section in doc.sections:
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)
    
    # 2. Configure 'Normal' style
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Times New Roman'
    normal_style.font.size = Pt(12)
    normal_style.paragraph_format.line_spacing = 1.05
    normal_style.paragraph_format.space_after = Pt(2.0)

    # 3. Remove consecutive blank paragraphs
    body_elements = doc._body._element
    prev_was_empty = False
    
    # Clean paragraphs
    for p in list(doc.paragraphs):
        txt = p.text.strip()
        if not txt:
            # Check if paragraph has images/drawings
            if not p._p.xpath('.//w:drawing'):
                if prev_was_empty:
                    # Remove redundant empty paragraph
                    p._p.getparent().remove(p._p)
                    continue
                prev_was_empty = True
            else:
                prev_was_empty = False
        else:
            prev_was_empty = False
            
        # Format paragraph rhythm
        p.paragraph_format.line_spacing = 1.05
        p.paragraph_format.space_after = Pt(2.0)
        
        is_h1 = (p.style.name == 'Heading 1' or txt.startswith('Chapter') or txt.startswith('CHAPTER') 
                 or txt in ['Candidate’s Declaration', 'Certificate', 'Acknowledgement', 
                            'Similarity Index Report', 'AI Usage Disclosure Statement', 
                            'Student Declaration', 'List of Abbreviations', 'List of Figures', 
                            'List of Tables', 'Abstract', 'Table of Contents', 'Bibliography', 'References'])
        is_h2 = p.style.name == 'Heading 2' or (len(txt) > 3 and txt[:3].replace('.', '').isdigit() and ' ' in txt[:6])

        if is_h1:
            p.paragraph_format.space_before = Pt(6.0)
            p.paragraph_format.space_after = Pt(2.5)
        elif is_h2:
            p.paragraph_format.space_before = Pt(4.0)
            p.paragraph_format.space_after = Pt(1.5)

        for r in p.runs:
            if r.font.name != 'Consolas':
                r.font.name = 'Times New Roman'
                if is_h1:
                    r.font.size = Pt(14)
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x8A)
                elif is_h2:
                    r.font.size = Pt(13)
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(0x2B, 0x4C, 0x7E)
                else:
                    if r.font.size is None:
                        r.font.size = Pt(12)

    # 4. Format Tables (Tight padding, Times New Roman 9.5pt header / 9pt data)
    for t in doc.tables:
        t.style = 'Light Grid Accent 1'
        for cell in t.rows[0].cells:
            set_cell_margins(cell, top=30, bottom=30, left=60, right=60)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(1.0)
                p.paragraph_format.line_spacing = 1.0
                for r in p.runs:
                    if r.font.name != 'Consolas':
                        r.font.name = 'Times New Roman'
                    r.font.size = Pt(9.5)
                    r.font.bold = True
        
        for row in t.rows[1:]:
            for cell in row.cells:
                set_cell_margins(cell, top=25, bottom=25, left=60, right=60)
                for p in cell.paragraphs:
                    p.paragraph_format.space_after = Pt(1.0)
                    p.paragraph_format.line_spacing = 1.0
                    for r in p.runs:
                        if r.font.name != 'Consolas':
                            r.font.name = 'Times New Roman'
                        r.font.size = Pt(9.0)

    # 5. Scale embedded drawing widths to 4.8 inches
    # In python-docx drawings are scaled via cx/cy EMU attributes in oxml
    for inline in doc._body._element.xpath('.//wp:inline'):
        extent = inline.find(qn('wp:extent'))
        if extent is not None:
            # 1 inch = 914400 EMUs -> 4.8 inches = 4389120 EMUs
            orig_cx = int(extent.get('cx', '0'))
            orig_cy = int(extent.get('cy', '0'))
            if orig_cx > 0 and orig_cy > 0:
                target_cx = 4389120  # 4.8 inches
                target_cy = int(orig_cy * (target_cx / orig_cx))
                extent.set('cx', str(target_cx))
                extent.set('cy', str(target_cy))

    doc.save(doc_path)
    doc.save(DOCS_MIRROR)
    print(f"✓ Optimized document layout saved to {doc_path} ({doc_path.stat().st_size:,} bytes)")

if __name__ == '__main__':
    tighten_document(DOC_PATH)
