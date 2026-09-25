#!/usr/bin/env python3
"""Explicitly refresh manuscript.typ from manuscript.md; does not compile it.

The .typ file is standalone and can be edited directly. Running this exporter
again replaces those direct edits, so use it only when refreshing from Markdown.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent
KEYS = {"1":"olguin2009sensible", "2":"lederman2017openbadges",
        "3":"kayhan2018signals", "4":"hall2009weka"}


def escape(text):
    return re.sub(r'([\\#*$@_<>\[\]])', r'\\\1', text)


def inline(source):
    tokens = re.compile(r'(`[^`]+`|\*\*.+?\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))')
    out = []
    for i, chunk in enumerate(tokens.split(source)):
        if i % 2 == 0:
            out.append(escape(chunk))
        elif chunk.startswith("`"):
            out.append(chunk)
        elif chunk.startswith("**"):
            out.append("*"+escape(chunk[2:-2])+"*")
        elif chunk.startswith("*"):
            out.append("_"+escape(chunk[1:-1])+"_")
        else:
            label, url = re.match(r'\[([^\]]+)\]\(([^)]+)\)', chunk).groups()
            if label in KEYS:
                out.append("@"+KEYS[label])
            else:
                out.append("#link("+json.dumps(url)+")["+escape(label)+"]")
    return "".join(out)


def main():
    blocks = (ROOT/"manuscript.md").read_text().strip().split("\n\n")
    out = [r'''// Standalone Typst manuscript. Compile from the repository root:
// typst compile paper/manuscript.typ paper/manuscript.pdf
// No online Typst packages are required.
#set document(
  title: "Estimating Perceived Meeting Effectiveness from Wearable Sound and Motion Signals: A Smart Badge Feasibility Study",
  author: ("Austin Sternberg", "Bishop Harsch", "JungYoon Kim"),
)
#set page(paper: "us-letter", margin: (x: 0.65in, top: 0.75in, bottom: 0.75in), columns: 2)
#set columns(gutter: 0.25in)
#set text(font: "Times New Roman", size: 10pt, lang: "en", hyphenate: false)
#set smartquote(enabled: false)
// Bibliography styles can insert Unicode punctuation even from ASCII input.
#show "\u{2013}": "-"
#show "\u{2014}": ": "
#show "\u{2018}": "'"
#show "\u{2019}": "'"
#show "\u{201c}": "\""
#show "\u{201d}": "\""
#set par(justify: true, leading: 0.45em, first-line-indent: 1em, spacing: 0.5em)
#set heading(numbering: none)
#set math.equation(numbering: "(1)")
#set figure(gap: 5pt)
#set table(inset: 3pt, stroke: 0.4pt)
#show heading.where(level: 1): it => block(width: 100%, above: 11pt, below: 6pt)[#set par(justify: false, first-line-indent: 0pt); #align(center)[#text(size: 10pt, weight: "regular")[#upper(it.body)]]]
#show heading.where(level: 2): it => block(above: 8pt, below: 4pt)[#text(size: 10pt, weight: "regular", style: "italic")[#it.body]]
#show figure.caption: set text(size: 8pt)
#show raw: set text(size: 7pt)
#let feature-table(columns, ..cells) = {
  set text(size: 8pt)
  set par(justify: false, first-line-indent: 0pt)
  table(columns: columns, ..cells)
}
#let ascii-equation(number, ..lines) = block(above: 7pt, below: 7pt, width: 100%)[
  #set par(justify: false, first-line-indent: 0pt)
  #grid(columns: (1fr, auto), column-gutter: 6pt, align: (center, right),
    text(size: 9pt, stack(dir: ttb, spacing: 2pt, ..lines.pos().map(line => text(line)))),
    [#text(size: 9pt)[(#number)]],
  )
]
''']
    equations = {
        1: '#ascii-equation(1, "v_i(t) = 1{m_i(t) > q_0.45^s(t)}.")\n\n'
           + inline('Here, m_i(t) is the 1 s sound mean, and q_p^x(t) is the rolling p-quantile of signal x_i over 60 s. The indicator 1{condition} equals 1 when the condition holds and 0 otherwise.'),
        2: '#ascii-equation(2, "z_i^x(t) = [x_i(t) - q_0.25^x(t)]", "/ max(q_0.75^x(t) - q_0.25^x(t), 1).")\n\n'
           + inline('Here, x is either sound s or acceleration a; ^x identifies the signal rather than an exponent.'),
        3: '#ascii-equation(3, "c_i(t) = z_i^s(t)", "+ 1.2 * clip(z_i^a(t), 0, 2.5).")',
        4: '#ascii-equation(4, "H = -sum_i(p_i * ln(p_i)) / ln(n).")',
        5: '#ascii-equation(5, "G = sum_i(sum_j(abs(d_i - d_j)))", "/ (2 * n * sum_i(d_i)).")',
    }
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.startswith(("**Manuscript draft", "**[AUTHOR QUERY:")):
            i += 1
            continue
        if block == "## References":
            out.append('#bibliography("references.bib", style: "ieee", title: [References])')
            break
        if block.startswith("# "):
            title = inline(block[2:])
            title = title.replace(' from Wearable', ' \\\nfrom Wearable').replace(': A Smart', ': \\\nA Smart')
            authors = inline(blocks[i+1])
            affiliation = inline(blocks[i+2])
            out.append('#place(top + center, float: true, scope: "parent", clearance: 18pt)[\n#block(width: 100%)[\n#set par(justify: false, first-line-indent: 0pt)\n#set text(hyphenate: false)\n#align(center)[\n#text(size: 22pt, weight: "regular")['+title+']\n\n#v(8pt)\n#text(size: 11pt)['+authors+']\n\n#text(size: 10pt)['+affiliation+']\n]\n]\n]')
            i += 2
        elif block.startswith("##"):
            heading = re.match(r'^(#+) (.*)$', block)
            title = heading[2]
            if title == "Abstract":
                out.append('*Abstract: *'+inline(blocks[i+1]))
                i += 1
            else:
                roman = {"1":"I", "2":"II", "3":"III", "4":"IV", "5":"V", "6":"VI"}
                if len(heading[1]) == 2:
                    title = re.sub(r'^(\d+)\.',lambda m:roman[m[1]]+'.',title)
                else:
                    title = re.sub(r'^\d+\.(\d+)\.',lambda m:chr(64+int(m[1]))+'.',title)
                out.append("="*(len(heading[1])-1)+" "+inline(title))
        elif block.startswith("**Equation"):
            n = int(re.match(r'\*\*Equation (\d+)',block)[1])
            out.append(equations[n])
        elif block.startswith("| "):
            rows = block.splitlines()
            cols = len(rows[0].strip("|").split("|"))
            widths = "(1.1fr, 3.4fr, 0.6fr)" if "Number" in rows[0] else "(1.2fr, 3.5fr)" if cols==2 else "(2fr, 1fr, 1fr)"
            cells = []
            for row_index, row in enumerate(rows):
                if row_index == 1:
                    continue
                cell_contents = ["["+inline(c.strip())+"]" for c in row.strip("|").split("|")]
                if row_index == 0:
                    cells.append("table.header("+", ".join(cell_contents)+"),")
                else:
                    cells.append(", ".join(cell_contents)+",")
            table = '#feature-table('+widths+',\n  '+"\n  ".join(cells)+'\n)'
            if out and out[-1].startswith("// TABLE_CAPTION "):
                caption = out.pop().removeprefix("// TABLE_CAPTION ")
                out.append('#figure(\n  '+table.removeprefix("#")+',\n  kind: table, supplement: [Table],\n  caption: ['+caption+'],\n)')
            else:
                out.append(table)
        elif block.startswith("*Table "):
            out.append("// TABLE_CAPTION "+inline(re.sub(r'^\*Table \d+\. ', '', block)[:-1]))
        elif block.startswith("!["):
            alt, path = re.match(r'!\[([^\]]*)\]\(([^)]+)\)',block).groups()
            caption = blocks[i+1]
            assert caption.startswith("*Figure ")
            caption = re.sub(r'^\*Figure \d+\. ', '',caption)[:-1]
            out.append('#figure(\n  image('+json.dumps(path.replace('.png','.svg'))+', width: 100%, alt: '+json.dumps(alt)+'),\n  placement: top, scope: "parent",\n  caption: ['+inline(caption)+'],\n)')
            i += 1
        else:
            # Keep author administration in the companion notes, not the paper.
            block = re.sub(r'\*\*\[AUTHOR QUERY:.*?\]\*\*', '', block)
            out.append(inline(block.strip()))
        i += 1
    (ROOT/"manuscript.typ").write_text("\n\n".join(out)+"\n")
    print("Wrote manuscript.typ; compile with: typst compile paper/manuscript.typ paper/manuscript.pdf")


if __name__ == "__main__":
    main()
