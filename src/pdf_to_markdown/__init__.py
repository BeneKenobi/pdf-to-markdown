"""Local PDF -> Markdown conversion (Docling, with OCR for scans)."""

import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

console = Console()


def collect_pdfs(inputs: tuple[Path, ...], recursive: bool) -> list[tuple[Path, Path]]:
    """(pdf, path relative to its own root) per input, deduplicated."""
    pattern = "**/*.pdf" if recursive else "*.pdf"
    out: dict[Path, Path] = {}
    for item in inputs:
        if item.is_dir():
            for pdf in sorted(item.glob(pattern, case_sensitive=False)):
                out.setdefault(pdf.resolve(), pdf.relative_to(item))
        elif item.suffix.lower() == ".pdf":
            out.setdefault(item.resolve(), Path(item.name))
    return list(out.items())


def _pick_device(choice: str) -> str:
    """Docling's AUTO picks the CPU on Apple Silicon - MPS is ~5x faster there."""
    if choice != "auto":
        return choice
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "auto"


@click.command()
@click.argument(
    "inputs",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "-o",
    "--output-dir",
    default="markdown_output",
    type=click.Path(file_okay=False, path_type=Path),
    help="Target directory for the .md files.",
)
@click.option("--ocr/--no-ocr", default=True, help="OCR for scanned PDFs (default: on).")
@click.option(
    "--device",
    type=click.Choice(["auto", "mps", "cuda", "cpu", "xpu"]),
    default="auto",
    help="Compute device. auto uses the GPU when available (~5x faster than CPU).",
)
@click.option("-r", "--recursive", is_flag=True, help="Search subdirectories as well.")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing .md files.")
def main(
    inputs: tuple[Path, ...],
    output_dir: Path,
    ocr: bool,
    device: str,
    recursive: bool,
    force: bool,
) -> None:
    """Convert PDFs (files or directories) to Markdown, locally."""
    jobs = collect_pdfs(inputs, recursive)
    if not jobs:
        raise click.ClickException("No PDFs found.")

    if not force:
        jobs = [(p, r) for p, r in jobs if not (output_dir / r).with_suffix(".md").exists()]
        if not jobs:
            console.print("[yellow]Everything already converted (--force to overwrite).[/]")
            return

    # Docling/RapidOCR would otherwise log across the progress bar, incl. a WARNING per blank page
    logging.disable(logging.WARNING)
    with console.status("Loading Docling models ..."):
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = ocr
        opts.do_table_structure = True
        opts.accelerator_options = AcceleratorOptions(
            num_threads=os.cpu_count() or 4,
            device=AcceleratorDevice(_pick_device(device)),
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
        converter.initialize_pipeline(InputFormat.PDF)  # load models here, not in the progress bar

    failed: list[tuple[Path, Exception]] = []
    empty: list[Path] = []
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(compact=True),
        TextColumn("[dim]{task.fields[file]}"),
        console=console,
    )
    with progress:
        task = progress.add_task("Converting", total=len(jobs), file="")
        for pdf, rel in jobs:
            progress.update(task, file=rel.name)
            target = (output_dir / rel).with_suffix(".md")
            try:
                markdown = converter.convert(pdf).document.export_to_markdown()
            except Exception as exc:  # one broken file must not kill the batch
                failed.append((pdf, exc))
                progress.advance(task)
                continue
            if len(markdown.strip()) < 32:
                empty.append(pdf)  # OCR found nothing - scan too dark or skewed?
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(".md.part")  # write first, then rename: an abort
            part.write_text(markdown, encoding="utf-8")  # leaves no half file behind that
            part.replace(target)  # the next run would skip as already done
            progress.advance(task)

    console.print(f"[green]{len(jobs) - len(failed)} file(s) -> {output_dir}[/]")
    for pdf, exc in failed:
        console.print(f"[red]Failed[/] {pdf.name}: {exc}")
    for pdf in empty:
        console.print(f"[yellow]Empty[/] {pdf.name}: no text recognized, please check")
