#!/usr/bin/env python3
"""Export manuscript.md to an editable Word document, manuscript.docx.

The layout mirrors manuscript.typ: US Letter, 10-point Times New Roman, a
full-width title block, and a two-column body. Equations are written as native
Word math (OMML), so they stay editable in Word's equation editor. Requires python-docx
(`pip install python-docx`). Neither manuscript.md nor manuscript.typ is modified.
"""
from pathlib import Path
import re

try:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Inches, Pt, RGBColor
except ImportError:
    raise SystemExit("Install python-docx (pip install python-docx), then rerun this script.")

ROOT = Path(__file__).resolve().parent
FONT = "Times New Roman"
MARGIN_X, GUTTER = 0.65, 0.25
COLUMN = (8.5 - 2*MARGIN_X - GUTTER) / 2
ROMAN = {"1":"I", "2":"II", "3":"III", "4":"IV", "5":"V", "6":"VI"}
# Equations and their definitions, in the small LaTeX-like notation read by math().
EQUATIONS = {
    1: (r"v_i(t) = \one\brace{m_i(t) > q_{0.45}^s(t)}.",
        r"Here, $m_i(t)$ is the 1 s sound mean, and $q_p^x(t)$ is the rolling $p$-quantile of signal $x_i$ over 60 s. The indicator $\one\brace{\op{condition}}$ equals 1 when the condition holds and 0 otherwise."),
    2: (r"z_i^x = \frac{x_i - q_{0.25}^x}{\fn{\op{max}}{\paren{\op{IQR}_i^x, 1}}}.",
        r"Here, $x$ is either sound $s$ or acceleration $a$; the superscript $x$ identifies the signal rather than an exponent. Time arguments are omitted in (2), and $\op{IQR}_i^x = q_{0.75}^x - q_{0.25}^x$."),
    3: (r"c_i(t) = z_i^s(t) + 1.2 \cdot \fn{\op{clip}}{\paren{z_i^a(t), 0, 2.5}}.", None),
    4: (r"H = -\frac{\sum_i{p_i \fn{\op{ln}}{p_i}}}{\fn{\op{ln}}{n}}.", None),
    5: (r"G = \frac{\sum_i{\sum_j{\abs{d_i - d_j}}}}{2n \sum_i{d_i}}.", None),
}
# ASCII math in the Markdown body text, typeset as inline Word math.
INLINE_MATH = {
    "s_i(t)": "$s_i(t)$",
    "a_i(t)": "$a_i(t)$",
    "badge i": "badge $i$",
    "participant i": "participant $i$",
    "p_i = d_i / sum_j(d_j)": r"$p_i = d_i / \sum_j{d_j}$",
    "max_i(p_i)": r"$\fn{\op{max}_i}{p_i}$",
    "d_i": "$d_i$",
    "(n - 1)/n": "$(n - 1)/n$",
}
INLINE_PATTERN = re.compile("|".join(
    r'(?<![\w$])' + re.escape(k) + r'(?![\w$])' for k in sorted(INLINE_MATH, key=len, reverse=True)))
DELIMITERS = {"paren": "()", "brace": "{}", "abs": "||"}
TABLE_WIDTHS = {"Number": (1.0, 3.3, 0.85), "Session-held-out": (1.6, 0.7, 1.1), 2: (1.2, 3.5), 3: (2, 1, 1)}


def math(source, display=False):
    r"""Translate a small LaTeX-like subset into a Word math (OMML) element.

    Supported: _ and ^ scripts, {groups}, \frac{a}{b}, \sum_i{body}, \op{upright
    text}, \fn{name}{argument}, \paren{}, \brace{}, \abs{}, \one, and \cdot.
    """
    def run(text, style=None):
        # Upright text is marked as normal text so that Word and LibreOffice agree.
        props = "<m:rPr><m:nor/></m:rPr>" if style else ""
        bold = "<w:b/>" if style == "b" else ""
        return ('<m:r>%s<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>%s'
                '<w:sz w:val="20"/></w:rPr>'
                '<m:t xml:space="preserve">%s</m:t></m:r>'
                % (props, bold, text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")))

    def sequence(i, stop=None):
        out = []
        while i < len(source) and source[i] != stop:
            if source[i] == " ":
                i += 1
                continue
            base, i = atom(i)
            scripts = {}
            while i < len(source) and source[i] in "_^":
                kind = source[i]
                scripts[kind], i = argument(i+1)
            if len(scripts) == 2:
                base = "<m:sSubSup><m:e>%s</m:e><m:sub>%s</m:sub><m:sup>%s</m:sup></m:sSubSup>" % (
                    base, scripts["_"], scripts["^"])
            elif "_" in scripts:
                base = "<m:sSub><m:e>%s</m:e><m:sub>%s</m:sub></m:sSub>" % (base, scripts["_"])
            elif "^" in scripts:
                base = "<m:sSup><m:e>%s</m:e><m:sup>%s</m:sup></m:sSup>" % (base, scripts["^"])
            out.append(base)
        return "".join(out), i

    def argument(i):
        if source[i] == "{":
            xml, i = sequence(i+1, "}")
            return xml, i+1
        return atom(i)

    def atom(i):
        c = source[i]
        if c == "{":
            return argument(i)
        if c == "\\" and source[i+1].isalpha():
            name = re.match(r'[a-z]+', source[i+1:])[0]
            i += 1 + len(name)
            if name == "frac":
                num, i = argument(i)
                den, i = argument(i)
                return "<m:f><m:num>%s</m:num><m:den>%s</m:den></m:f>" % (num, den), i
            if name == "sum":
                index, i = argument(i+1)
                body, i = argument(i)
                return ('<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="%s"/>'
                        '<m:supHide m:val="1"/></m:naryPr><m:sub>%s</m:sub><m:sup/><m:e>%s</m:e></m:nary>'
                        % ("undOvr" if display else "subSup", index, body)), i
            if name == "op":
                end = source.index("}", i)
                return run(source[i+1:end], "p"), end+1
            if name == "fn":
                label, i = argument(i)
                body, i = argument(i)
                return "<m:func><m:fName>%s</m:fName><m:e>%s</m:e></m:func>" % (label, body), i
            if name in DELIMITERS:
                body, i = argument(i)
                return ('<m:d><m:dPr><m:begChr m:val="%s"/><m:endChr m:val="%s"/></m:dPr><m:e>%s</m:e></m:d>'
                        % (*DELIMITERS[name], body)), i
            if name == "one":
                return run("1", "b"), i
            if name == "cdot":
                return run("⋅"), i
            raise ValueError("Unknown math command \\" + name)
        number = re.match(r'\d+(\.\d+)?', source[i:])
        if number:
            return run(number[0]), i + len(number[0])
        return run("−" if c == "-" else c), i+1

    return parse_xml("<m:oMath %s>%s</m:oMath>" % (nsdecls("m", "w"), sequence(0)[0]))


def hyperlink(paragraph, url, text, size=None):
    rel = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel)
    run = paragraph.add_run(text)
    run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x93)
    if size:
        run.font.size = size
    link.append(run._r)
    paragraph._p.append(link)


def inline(paragraph, source, size=None, citations=True):
    tokens = re.compile(r'(\$[^$]+\$|`[^`]+`|\*\*.+?\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))')
    for i, chunk in enumerate(tokens.split(source)):
        if not chunk:
            continue
        if i % 2 == 0:
            run = paragraph.add_run(chunk)
        elif chunk.startswith("$"):
            paragraph._p.append(math(chunk[1:-1]))
            continue
        elif chunk.startswith("`"):
            run = paragraph.add_run(chunk[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(7.5)
            continue
        elif chunk.startswith("**"):
            run = paragraph.add_run(chunk[2:-2])
            run.bold = True
        elif chunk.startswith("*"):
            run = paragraph.add_run(chunk[1:-1])
            run.italic = True
        else:
            label, url = re.match(r'\[([^\]]+)\]\(([^)]+)\)', chunk).groups()
            if citations and label.isdigit():
                # Citations follow the preceding sentence, as in the IEEE style.
                if paragraph.runs and paragraph.runs[-1].text.endswith(" "):
                    paragraph.runs[-1].text = paragraph.runs[-1].text.rstrip()
                run = paragraph.add_run(" ["+label+"]")
            else:
                hyperlink(paragraph, url, label, size)
                continue
        if size:
            run.font.size = size


def set_columns(section, count):
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), str(count))
    cols.set(qn("w:space"), str(int(GUTTER*1440)))


def plain(doc, align=None, indent=True, size=None, before=0, after=0):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    if align is not None:
        p.alignment = align
    if not indent:
        fmt.first_line_indent = Pt(0)
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    return p


def caption(doc, text):
    p = plain(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, indent=False, before=3, after=6)
    label, body = re.match(r'\*((?:Figure|Table) \d+\.) (.*)\*$', text).groups()
    p.add_run(label+" ").font.size = Pt(8)
    inline(p, body, Pt(8))
    return p


def table(doc, block):
    rows = [[c.strip() for c in r.strip().strip("|").split("|")]
            for r in block.splitlines()]
    del rows[1]
    key = next((k for k in TABLE_WIDTHS if isinstance(k, str) and k in "|".join(rows[0])), len(rows[0]))
    widths = TABLE_WIDTHS[key]
    scale = COLUMN / sum(widths)
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(layout)
    for c, column in enumerate(t.columns):
        column.width = Inches(widths[c]*scale)
    for r, row in enumerate(rows):
        if r == 0:
            header = OxmlElement("w:tblHeader")
            t.rows[0]._tr.get_or_add_trPr().append(header)
        for c, text in enumerate(row):
            cell = t.cell(r, c)
            cell.width = Inches(widths[c]*scale)
            p = cell.paragraphs[0]
            p.paragraph_format.first_line_indent = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            inline(p, "**"+text+"**" if r == 0 else text, Pt(8))
    plain(doc, indent=False, after=4).paragraph_format.line_spacing = Pt(4)


def equation(doc, number):
    source, note = EQUATIONS[number]
    # A borderless table keeps the equation centered in display style with its
    # number flush right, in both Word and LibreOffice.
    widths = (0.35, COLUMN-0.7, 0.35)
    t = doc.add_table(rows=1, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(layout)
    t._tbl.tblPr.append(parse_xml(
        '<w:tblCellMar %s><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar>'
        % nsdecls("w")))
    for c, align in enumerate((WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT)):
        t.columns[c].width = Inches(widths[c])
        cell = t.cell(0, c)
        cell.width = Inches(widths[c])
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(5)
    para = parse_xml('<m:oMathPara %s><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr></m:oMathPara>'
                     % nsdecls("m"))
    para.append(math(source, display=True))
    t.cell(0, 1).paragraphs[0]._p.append(para)
    t.cell(0, 2).paragraphs[0].add_run("(%d)" % number)
    if note:
        inline(plain(doc, WD_ALIGN_PARAGRAPH.JUSTIFY), note)


def setup(doc):
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Inches(MARGIN_X)
    section.top_margin = section.bottom_margin = Inches(0.75)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    fmt = normal.paragraph_format
    fmt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    fmt.first_line_indent = Pt(10)
    fmt.space_before = fmt.space_after = Pt(0)
    fmt.line_spacing = 1.0
    for level, italic in ((1, False), (2, True)):
        style = doc.styles["Heading %d" % level]
        style.font.name = FONT
        style.font.size = Pt(10)
        style.font.bold = False
        style.font.italic = italic
        style.font.color.rgb = RGBColor(0, 0, 0)
        rfonts = style.element.rPr.rFonts
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            rfonts.attrib.pop(qn(attr), None)
        style.font.all_caps = level == 1
        pf = style.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
        pf.first_line_indent = Pt(0)
        pf.space_before, pf.space_after = (Pt(11), Pt(6)) if level == 1 else (Pt(8), Pt(4))
        pf.keep_with_next = True


def main():
    blocks = (ROOT/"manuscript.md").read_text().strip().split("\n\n")
    doc = Document()
    setup(doc)
    i = 0
    while i < len(blocks):
        block = blocks[i].strip()
        if block.startswith(("**Manuscript draft", "**[AUTHOR QUERY:")):
            pass
        elif block.startswith("# "):
            title, authors, affiliation = block[2:], blocks[i+1], blocks[i+2]
            doc.core_properties.title = title
            doc.core_properties.author = authors.replace(", and ", ", ").replace(" and ", ", ")
            p = plain(doc, WD_ALIGN_PARAGRAPH.CENTER, indent=False, after=8)
            p.add_run(title).font.size = Pt(22)
            p.paragraph_format.line_spacing = 1.0
            plain(doc, WD_ALIGN_PARAGRAPH.CENTER, indent=False).add_run(authors).font.size = Pt(11)
            plain(doc, WD_ALIGN_PARAGRAPH.CENTER, indent=False, after=18).add_run(affiliation)
            set_columns(doc.sections[0], 1)
            set_columns(doc.add_section(WD_SECTION.CONTINUOUS), 2)
            i += 2
        elif block == "## Abstract":
            p = plain(doc, WD_ALIGN_PARAGRAPH.JUSTIFY)
            p.add_run("Abstract: ").bold = True
            inline(p, blocks[i+1])
            i += 1
        elif block == "## References":
            doc.add_heading("References", 1)
            for ref in blocks[i+1:]:
                number, text = re.match(r'\[(\d+)\] (.*)', ref).groups()
                p = plain(doc, WD_ALIGN_PARAGRAPH.LEFT, after=2)
                p.paragraph_format.left_indent = Pt(18)
                p.paragraph_format.first_line_indent = Pt(-18)
                p.add_run("["+number+"]\t").font.size = Pt(8)
                p.paragraph_format.tab_stops.add_tab_stop(Pt(18))
                inline(p, text, Pt(8), citations=False)
            break
        elif block.startswith("##"):
            hashes, title = re.match(r'^(#+) (.*)$', block).groups()
            if len(hashes) == 2:
                title = re.sub(r'^(\d+)\.', lambda m: ROMAN[m[1]]+'.', title)
            else:
                title = re.sub(r'^\d+\.(\d+)\.', lambda m: chr(64+int(m[1]))+'.', title)
            doc.add_heading(title, len(hashes)-1)
        elif block.startswith("**Equation"):
            equation(doc, int(re.match(r'\*\*Equation (\d+)', block)[1]))
        elif block.startswith("*Table "):
            caption(doc, block).paragraph_format.keep_with_next = True
        elif block.startswith("| "):
            table(doc, block)
        elif block.startswith("!["):
            alt, path = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', block).groups()
            p = plain(doc, WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=4)
            p.paragraph_format.keep_with_next = True
            p.add_run().add_picture(str(ROOT/path), width=Inches(COLUMN))
            doc.inline_shapes[-1]._inline.docPr.set("descr", alt)
            caption(doc, blocks[i+1])
            i += 1
        else:
            block = re.sub(r'\*\*\[AUTHOR QUERY:.*?\]\*\*', '', block).strip()
            block = INLINE_PATTERN.sub(lambda m: INLINE_MATH[m[0]], block)
            inline(plain(doc, WD_ALIGN_PARAGRAPH.JUSTIFY), block)
        i += 1
    doc.save(ROOT/"manuscript.docx")
    print(f"Wrote {ROOT/'manuscript.docx'}")


if __name__ == "__main__":
    main()
