import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz
import pytesseract
from pdf2image import convert_from_bytes
from PyPDF2 import PdfReader, PdfWriter

import translation_service.env_config as ec
from translation_service.logger_utils import logger

_TEXT_THRESHOLD = ec.text_threshold  # chars per page below which we consider the page image-only
_DEFAULT_CHUNK_MB = ec.pdf_chunk_size_mb


def is_scanned_pdf(pdf_bytes: bytes) -> bool:
    """Returns True if the PDF has no extractable text on any page (i.e. is scanned)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            if len(page.get_text().strip()) > _TEXT_THRESHOLD:
                logger.info("Unscanned pdf detected")
                return False
        logger.info("Scanned pdf detected")
        return True
    finally:
        doc.close()


def pdf_pages_to_zip(pdf_bytes: bytes, dpi: int = 150) -> bytes:
    """Renders every page of a PDF as a PNG and returns a ZIP archive."""
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    buf = io.BytesIO()
    try:
        logger.info(f"Rendering {len(doc)} page(s) at {dpi} dpi")
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(doc):
                pixmap = page.get_pixmap(matrix=matrix)
                zf.writestr(f"page_{i + 1:04d}.png", pixmap.tobytes("png"))
    finally:
        doc.close()
    return buf.getvalue()


_TOBYTES_OPTS = {"garbage": 4, "deflate": True}


def split_pdf_into_chunks(pdf_bytes: bytes, max_chunk_mb: float = _DEFAULT_CHUNK_MB) -> list[bytes]:
    """Splits a PDF into chunks strictly below max_chunk_mb.

    garbage=4 + deflate on every tobytes() call gives a clean, accurate size so
    shared resources and stale cross-references don't cause the size check to lie.
    A single page that already exceeds the limit is kept as its own chunk (can't split further).
    """
    max_bytes = int(max_chunk_mb * 1024 * 1024)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[bytes] = []
    try:
        logger.info(f"Splitting {len(doc)}-page PDF into {max_chunk_mb} MB chunks")
        chunk_doc = fitz.open()
        for i in range(len(doc)):
            chunk_doc.insert_pdf(doc, from_page=i, to_page=i)
            serialized = chunk_doc.tobytes(**_TOBYTES_OPTS)
            if len(serialized) > max_bytes:
                if len(chunk_doc) == 1:
                    # Single page already exceeds limit — save as-is, nothing to split
                    logger.warning(
                        f"Page {i + 1} alone is {len(serialized) / 1024 / 1024:.1f} MB"
                        f", exceeds {max_chunk_mb} MB limit"
                    )
                    chunks.append(serialized)
                    chunk_doc = fitz.open()
                else:
                    chunk_doc.delete_page(-1)
                    chunks.append(chunk_doc.tobytes(**_TOBYTES_OPTS))
                    logger.info(f"Chunk {len(chunks)} saved, ended before page {i + 1}")
                    chunk_doc = fitz.open()
                    chunk_doc.insert_pdf(doc, from_page=i, to_page=i)
        if len(chunk_doc) > 0:
            chunks.append(chunk_doc.tobytes(**_TOBYTES_OPTS))
            logger.info(f"Chunk {len(chunks)} saved (final)")
    finally:
        doc.close()
    return chunks


def pdf_chunks_to_zip(pdf_bytes: bytes, max_chunk_mb: float = _DEFAULT_CHUNK_MB) -> bytes:
    """Splits the PDF into size-bounded chunks and returns them as a ZIP archive."""
    chunks = split_pdf_into_chunks(pdf_bytes, max_chunk_mb=max_chunk_mb)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, chunk in enumerate(chunks):
            zf.writestr(f"chunk_{i + 1:03d}.pdf", chunk)
    return buf.getvalue()


_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "tiff", "tif", "bmp", "gif", "webp"}


def merge_files_to_pdf(files: list[tuple[str, bytes]]) -> bytes:
    """Merges PDFs and images (in order) into a single PDF."""
    output = fitz.open()
    for filename, data in files:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "pdf":
            src = fitz.open(stream=data, filetype="pdf")
        elif ext in _IMAGE_EXTENSIONS:
            img_doc = fitz.open(stream=data, filetype=ext)
            src = fitz.open("pdf", img_doc.convert_to_pdf())
            img_doc.close()
        else:
            logger.warning(f"Skipping unsupported file: {filename}")
            continue
        output.insert_pdf(src)
        src.close()
    logger.info(f"Merged {len(output)} page(s) from {len(files)} file(s)")
    return output.tobytes(**_TOBYTES_OPTS)


def merge_zip_to_pdf(zip_bytes: bytes) -> bytes:
    """Extracts a ZIP and merges all PDFs and images inside into a single PDF."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = sorted(n for n in zf.namelist() if not n.endswith("/"))
        files = [(name, zf.read(name)) for name in names]
    logger.info(f"Extracted {len(files)} file(s) from ZIP")
    return merge_files_to_pdf(files)


_ALLOWED_LANGS = ec.ocr_languages
_TESSERACT_LANGS: str | None = None


def _get_all_langs() -> str:
    global _TESSERACT_LANGS
    if _TESSERACT_LANGS is None:
        installed = [lang for lang in pytesseract.get_languages() if lang in _ALLOWED_LANGS]
        _TESSERACT_LANGS = "+".join(installed)
        logger.info(f"Tesseract languages loaded: {_TESSERACT_LANGS}")
    return _TESSERACT_LANGS


def ocr_pdf(pdf_bytes: bytes) -> bytes:
    """Runs Tesseract OCR on every page in parallel and returns a searchable PDF."""
    tesseract_lang = _get_all_langs()
    images = convert_from_bytes(pdf_bytes)
    total = len(images)
    logger.info(f"OCR: processing {total} page(s) with lang={tesseract_lang!r}")

    page_results: list[bytes | None] = [None] * total

    def _ocr_page(idx: int, image) -> tuple[int, bytes]:
        result = pytesseract.image_to_pdf_or_hocr(image, lang=tesseract_lang, extension="pdf")
        logger.info(f"OCR: page {idx + 1}/{total} done")
        return idx, result

    with ThreadPoolExecutor(max_workers=ec.ocr_max_workers) as executor:
        futures = {executor.submit(_ocr_page, i, img): i for i, img in enumerate(images)}
        for future in as_completed(futures):
            idx, result = future.result()
            page_results[idx] = result

    writer = PdfWriter()
    for page_bytes in page_results:
        writer.add_page(PdfReader(io.BytesIO(page_bytes)).pages[0])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
