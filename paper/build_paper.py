#!/usr/bin/env python3
"""Compile the editable Typst source without regenerating or overwriting it."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent
compiler = shutil.which("typst") or str(root / ".tools" / "typst")
if not Path(compiler).is_file():
    raise SystemExit("Install Typst, then rerun this script. See paper/README.md.")
subprocess.run([compiler, "compile", "--font-path", str(root / ".fonts"),
                str(root / "manuscript.typ"), str(root / "manuscript.pdf")], check=True)
print(f"Compiled {root / 'manuscript.pdf'}")
