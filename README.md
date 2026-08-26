# pdf-to-markdown

Converts PDFs to Markdown locally via [Docling](https://github.com/docling-project/docling),
with OCR for scans. Nothing leaves the machine (models are downloaded once).

```bash
uv sync
uv run pdf-to-markdown applications/ -o markdown_output
uv run python tests/test_collect.py
```

INPUTS are files and/or directories, mixed freely.

| Option | |
|---|---|
| `-o, --output-dir` | target directory (default `markdown_output`) |
| `--ocr / --no-ocr` | OCR for scans, on by default; off is faster for native PDFs |
| `--device` | `auto` picks MPS/CUDA when available — ~5x faster than CPU |
| `-r, --recursive` | include subdirectories, structure preserved |
| `-f, --force` | overwrite existing `.md` instead of skipping them |

Aborted runs resume: finished files are kept and skipped. Broken PDFs and results where OCR
found no text are listed at the end rather than killing the batch.
