"""HTML → PDF (WeasyPrint) y PDF → PNG (pdfium)."""

import io
import os
from pathlib import Path

# En Windows, WeasyPrint necesita las DLL de Pango (MSYS2). En Linux/Docker vienen del sistema.
_MSYS_BIN = Path(r"C:\msys64\ucrt64\bin")
if os.name == "nt" and "WEASYPRINT_DLL_DIRECTORIES" not in os.environ and _MSYS_BIN.exists():
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(_MSYS_BIN)

import pypdfium2 as pdfium  # noqa: E402
from weasyprint import HTML  # noqa: E402
from weasyprint.text.fonts import FontConfiguration  # noqa: E402


def html_to_pdf(html: str, base_url: Path) -> bytes:
    fonts = FontConfiguration()
    return HTML(string=html, base_url=str(base_url)).write_pdf(font_config=fonts)


def pdf_page_to_png(pdf: bytes, page: int = 0, width: int = 1200) -> bytes:
    document = pdfium.PdfDocument(pdf)
    try:
        target = document[page]
        scale = width / target.get_width()
        image = target.render(scale=scale).to_pil()
    finally:
        document.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def pdf_page_count(pdf: bytes) -> int:
    document = pdfium.PdfDocument(pdf)
    try:
        return len(document)
    finally:
        document.close()
