"""Use the current PyMuPDF name without legacy import notices on MCP stdout."""

try:
    import pymupdf as fitz
except ModuleNotFoundError as exc:
    if exc.name != "pymupdf":
        raise
    import fitz  # Older supported PyMuPDF releases.
