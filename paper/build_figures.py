#!/usr/bin/env python3
"""Redraw manuscript diagrams and verify arithmetic from poster counts.

The figures are vector diagrams/tables. Counts are transcribed from the poster;
this script does not fit models or use participant-level study data.
"""
from pathlib import Path
from html import escape
import json
import subprocess

ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
POSTER = "https://www-s3-live.kent.edu/s3fs-root/s3fs-public/JY%20Sternberg%20Harsh.pdf?VersionId=UDDNdl8b1OoxyoSmzs3e4BogTn1_vq3P"
MATRICES = {
    "Random Forest": [[4, 1, 0], [0, 7, 0], [0, 0, 4]],
    "Multilayer perceptron": [[3, 2, 0], [0, 6, 1], [0, 0, 4]],
}


def metrics(c):
    support = [sum(row) for row in c]
    predicted = [sum(row[j] for row in c) for j in range(3)]
    n = sum(support)
    accuracy = sum(c[i][i] for i in range(3)) / n
    expected = sum(a*b for a, b in zip(support, predicted)) / n**2
    precision = [c[i][i] / predicted[i] for i in range(3)]
    recall = [c[i][i] / support[i] for i in range(3)]
    f1 = [2*c[i][i] / (support[i]+predicted[i]) for i in range(3)]
    return dict(matrix=c, support=support, accuracy=accuracy,
                kappa=(accuracy-expected)/(1-expected), precision=precision,
                recall=recall, f1=f1, macro_f1=sum(f1)/3,
                balanced_accuracy=sum(recall)/3)


def text(x, y, content, size=18, color="#000000", weight="normal", anchor="middle"):
    return (f'<text x="{x}" y="{y}" font-family="Times New Roman, serif" '
            f'font-size="{size}" fill="{color}" font-weight="{weight}" '
            f'text-anchor="{anchor}">{escape(content)}</text>')


def svg_start(w, h):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="white"/>'


def save_figure(name, svg):
    path = FIGURES / f"{name}.svg"
    path.write_text(svg + "</svg>")
    subprocess.run(["rsvg-convert", "-z", "2", "-o", str(FIGURES/f"{name}.png"), str(path)], check=True)
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(FIGURES/f"{name}.pdf"), str(path)], check=True)


def make_figures():
    FIGURES.mkdir(exist_ok=True)
    # A graphic table, with exact counts and row-normalized cell shading.
    svg = svg_start(1080, 430)
    labels = ["Low", "Medium", "High"]
    for offset, (name, matrix) in zip([0, 545], MATRICES.items()):
        svg += text(offset+270, 32, name, 23, weight="bold")
        svg += text(offset+22, 225, "Actual", 17, anchor="start")
        for r in range(3):
            svg += text(offset+150, 122+r*90, labels[r], 17, anchor="end")
            for c in range(3):
                fraction = matrix[r][c]/sum(matrix[r])
                color = "#333333" if fraction >= .8 else "#bbbbbb" if fraction >= .5 else "#dddddd" if fraction > 0 else "#ffffff"
                x, y = offset+165+c*100, 67+r*90
                svg += f'<rect x="{x}" y="{y}" width="100" height="90" fill="{color}" stroke="white" stroke-width="2"/>'
                svg += text(x+50, y+56, str(matrix[r][c]), 30, "white" if fraction >= .8 else "#000000", "bold")
        for c in range(3):
            svg += text(offset+215+c*100, 365, labels[c], 17)
        svg += text(offset+315, 402, "Predicted label", 19)
    save_figure("confusion_matrices", svg)

    svg = svg_start(1080, 330)
    svg += '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#000000"/></marker></defs>'
    entries = [
        (10, 25, "1  Wearable badges", "Sound level / motion / RSSI"),
        (380, 25, "2  BLE host / CSV", "Allowlist / receipt timestamps"),
        (750, 25, "3  Speaker estimation", "500 ms / vote / smoothing"),
        (750, 215, "4  Feature extraction", "Meeting / participant / 5 min"),
        (380, 215, "5  WEKA export", "36 predictors + rating"),
        (10, 215, "6  Classification", "Low / medium / high"),
    ]
    for x, y, title, description in entries:
        svg += f'<rect x="{x}" y="{y}" width="320" height="90" rx="0" fill="#ffffff" stroke="#000000"/>'
        svg += text(x+160, y+35, title, 22, weight="bold")
        svg += text(x+160, y+66, description, 18)
    for x1,y1,x2,y2 in [(336,70,373,70),(706,70,743,70),(910,122,910,206),(743,260,706,260),(373,260,336,260)]:
        svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#000000" stroke-width="2" marker-end="url(#arrow)"/>'
    save_figure("pipeline", svg)



def main():
    computed = {name: metrics(matrix) for name, matrix in MATRICES.items()}
    assert round(computed["Random Forest"]["kappa"], 4) == .9024
    assert round(computed["Multilayer perceptron"]["kappa"], 4) == .7091
    (ROOT/"derived_metrics.json").write_text(json.dumps(dict(
        source=POSTER,
        provenance="Integer confusion matrices visually transcribed from supplied poster; no new model training.",
        class_order=["low", "medium", "high"], results=computed), indent=2)+"\n")
    make_figures()
    print("Updated figures and derived_metrics.json")


if __name__ == "__main__":
    main()
