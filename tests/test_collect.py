"""Self-check: uv run python tests/test_collect.py"""

import tempfile
from pathlib import Path

from pdf_to_markdown import collect_pdfs


def test_collect() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sub").mkdir()
        for name in ("a.pdf", "b.PDF", "notes.txt", "sub/a.pdf"):
            (root / name).touch()

        flat = collect_pdfs((root,), recursive=False)
        assert sorted(r.as_posix() for _, r in flat) == ["a.pdf", "b.PDF"], flat

        deep = collect_pdfs((root,), recursive=True)
        assert "sub/a.pdf" in [r.as_posix() for _, r in deep], deep

        # same file twice (as file and via directory) -> only one job
        both = collect_pdfs((root, root / "a.pdf"), recursive=False)
        assert len(both) == 2, both

        # a single file lands flat in the output directory
        single = collect_pdfs((root / "sub" / "a.pdf",), recursive=False)
        assert [r.as_posix() for _, r in single] == ["a.pdf"], single


if __name__ == "__main__":
    test_collect()
    print("ok")
