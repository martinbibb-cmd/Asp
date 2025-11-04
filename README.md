# Asp

Utilities and helpers for working with ASP price books.

## Converting the PDF price book to JSON

The repository includes a helper script that parses the bundled
`Manual_Pricebook_28.05.2025 - Updated.pdf` file and turns it into a JSON array
that can be consumed by other tooling (for example the web client in
`index.html`). Each JSON entry contains the part code, description and price.

```bash
python tools/pdf_to_pricebook.py --out pricebook.json
```

The script automatically locates the PDF that ships with the project and does
not require any third-party Python packages. You can override the input file by
passing `--pdf /path/to/another.pdf`. Use `--compact` if you prefer a
single-line JSON output.
