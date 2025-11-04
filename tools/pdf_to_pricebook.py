import pdfplumber
import json
import re
from pathlib import Path

PDF_NAME = "Manual Pricebook_28.05.2025 - Updated.pdf"  # change if your filename is different
OUT_NAME = "pricebook.json"

pdf_path = Path(PDF_NAME)
if not pdf_path.exists():
    raise SystemExit(f"PDF not found: {pdf_path}")

rows = []

# this tries to match lines like:
# p1949 Minor building work £150.00
line_re = re.compile(r"^(p?\d{3,5})\s+(.*?)\s+£?(\d+(?:\.\d{1,2})?)$")

with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            line = line.strip()
            m = line_re.match(line)
            if m:
                code = m.group(1)
                desc = m.group(2).strip()
                price = float(m.group(3))
                rows.append({
                    "code": code,
                    "description": desc,
                    "price": price
                })

with open(OUT_NAME, "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=2)

print(f"wrote {len(rows)} items to {OUT_NAME}")
