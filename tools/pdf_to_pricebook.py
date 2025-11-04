"""Utility to extract pricebook data from the bundled PDF.

This script reads the pricebook PDF that lives in the root of the repository
and produces a ``pricebook.json`` file containing a list of objects with
``code``, ``description`` and ``price`` keys.  The JSON can then be used as a
source of part codes and descriptions by the web front-end or any other tool.

The implementation avoids third-party PDF dependencies so it can run in
restricted environments (like this kata) where installing packages such as
``pdfplumber`` is not possible.  It performs just enough PDF parsing to decode
the text objects used in the ASP price book.
"""

from __future__ import annotations

import argparse
import json
import re
import zlib
from pathlib import Path

DEFAULT_OUT_NAME = "pricebook.json"

# ``CACU0001`` or ``P100`` etc – uppercase alphanumeric strings containing at
# least one letter and one digit.  Pricebook codes are between 4 and 8
# characters long.
CODE_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{4,8}$")

PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)")

# Rough-and-ready pattern to find PDF ``stream`` objects.  We do not attempt to
# parse the entire PDF grammar – we only need to locate Flate encoded streams so
# we can scan the text operators they contain.
STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)


def detect_pdf(explicit: str | None) -> Path:
    """Return the path to the pricebook PDF.

    If ``explicit`` is supplied we simply return that path (after verifying it
    exists). Otherwise we look for a PDF that matches the naming convention
    used in the repository (``Manual_Pricebook*.pdf``).
    """

    if explicit:
        pdf_path = Path(explicit)
        if not pdf_path.exists():
            raise SystemExit(f"PDF not found: {pdf_path}")
        return pdf_path

    repo_root = Path(__file__).resolve().parents[1]
    candidates = sorted(repo_root.glob("Manual*Pricebook*.pdf"))
    if not candidates:
        raise SystemExit(
            "Could not locate a pricebook PDF. Specify it explicitly with --pdf"
        )
    return candidates[0]


def decode_pdf_string(raw: str) -> str:
    """Decode a PDF literal string."""

    result: list[str] = []
    i = 0
    length = len(raw)
    while i < length:
        char = raw[i]
        if char == "\\":
            i += 1
            if i >= length:
                break
            esc = raw[i]
            if esc in "\\()":
                result.append(esc)
            elif esc == "n":
                result.append("\n")
            elif esc == "r":
                result.append("\r")
            elif esc == "t":
                result.append("\t")
            elif esc == "b":
                result.append("\b")
            elif esc == "f":
                result.append("\f")
            elif esc in "01234567":
                # Octal escape, up to three digits.
                oct_digits = esc
                j = 1
                while i + j < length and j < 3 and raw[i + j] in "01234567":
                    oct_digits += raw[i + j]
                    j += 1
                i += j - 1
                result.append(chr(int(oct_digits, 8)))
            else:
                result.append(esc)
        else:
            result.append(char)
        i += 1
    return "".join(result)


def iter_text_fragments(pdf_bytes: bytes) -> Iterator[str]:
    """Yield decoded text fragments from the PDF."""

    for match in STREAM_RE.finditer(pdf_bytes):
        stream = match.group(1)
        try:
            decoded = zlib.decompress(stream)
        except Exception:
            continue
        text = decoded.decode("latin1", errors="ignore")
        pos = 0
        while True:
            idx_tj = text.find("Tj", pos)
            idx_TJ = text.find("TJ", pos)
            if idx_tj == -1 and idx_TJ == -1:
                break
            if idx_tj == -1 or (idx_TJ != -1 and idx_TJ < idx_tj):
                idx = idx_TJ
                start = text.rfind("[", 0, idx)
                if start == -1:
                    pos = idx + 2
                    continue
                raw_array = text[start + 1 : idx]
                fragments: list[str] = []
                i = 0
                while i < len(raw_array):
                    if raw_array[i] == "(":
                        i += 1
                        token: list[str] = []
                        while i < len(raw_array):
                            ch = raw_array[i]
                            if ch == "\\" and i + 1 < len(raw_array):
                                token.append(raw_array[i])
                                token.append(raw_array[i + 1])
                                i += 2
                                continue
                            if ch == ")":
                                break
                            token.append(ch)
                            i += 1
                        fragments.append(decode_pdf_string("".join(token)))
                    else:
                        i += 1
                if fragments:
                    yield "".join(fragments)
                pos = idx + 2
            else:
                idx = idx_tj
                start = text.rfind("(", 0, idx)
                if start == -1:
                    pos = idx + 2
                    continue
                raw_string = text[start + 1 : idx]
                yield decode_pdf_string(raw_string)
                pos = idx + 2


def extract_rows(pdf_path: Path) -> list[dict[str, object]]:
    pdf_bytes = pdf_path.read_bytes()
    fragments = list(iter_text_fragments(pdf_bytes))

    rows: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    i = 0
    while i < len(fragments):
        candidate = fragments[i].strip()
        if not candidate:
            i += 1
            continue
        if CODE_RE.match(candidate):
            if i + 2 >= len(fragments):
                break
            description = " ".join(fragments[i + 1].split())
            price_fragment = fragments[i + 2]
            price_match = PRICE_RE.search(price_fragment)
            if not price_match:
                i += 1
                continue
            price = float(price_match.group(1).replace(",", ""))
            code = candidate.upper()
            if code not in seen_codes:
                rows.append(
                    {
                        "code": code,
                        "description": description,
                        "price": price,
                    }
                )
                seen_codes.add(code)
            # Skip the code, description, price and the trailing lead-time cell.
            i += 4
            continue
        i += 1
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract pricebook data from PDF")
    parser.add_argument(
        "--pdf",
        metavar="PATH",
        help="Path to the pricebook PDF (defaults to detecting the bundled file)",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=DEFAULT_OUT_NAME,
        help=f"Output JSON file (default: {DEFAULT_OUT_NAME})",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON (default is pretty-printed)",
    )
    args = parser.parse_args()

    pdf_path = detect_pdf(args.pdf)
    rows = extract_rows(pdf_path)

    if not rows:
        raise SystemExit("No rows extracted – is this the expected price book PDF?")

    out_path = Path(args.out)
    if args.compact:
        out_path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    else:
        out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
