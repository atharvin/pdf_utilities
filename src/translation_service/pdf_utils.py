import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz
import pytesseract
from PIL import Image as PIL_Image
from PyPDF2 import PdfReader, PdfWriter

import translation_service.env_config as ec
from translation_service.logger_utils import logger

_TEXT_THRESHOLD = ec.text_threshold  # chars per page below which we consider the page image-only
_DEFAULT_CHUNK_MB = ec.pdf_chunk_size_mb
_DEFAULT_CHUNK_MAX_PAGES = ec.pdf_chunk_max_pages


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


def pdf_pages_to_zip(pdf_bytes: bytes, dpi: int = 150, jpeg_quality: int = 85) -> bytes:
    """Renders every page of a PDF as a JPEG and returns a ZIP archive."""
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    buf = io.BytesIO()
    try:
        logger.info(f"Rendering {len(doc)} page(s) at {dpi} dpi, jpeg_quality={jpeg_quality}")
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(doc):
                pixmap = page.get_pixmap(matrix=matrix)
                if pixmap.alpha:
                    pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                zf.writestr(f"page_{i + 1:04d}.jpg", pixmap.tobytes("jpeg", jpg_quality=jpeg_quality))
    finally:
        doc.close()
    return buf.getvalue()


_TOBYTES_OPTS = {"garbage": 4, "deflate": True}


def split_pdf_into_chunks(
    pdf_bytes: bytes,
    max_chunk_mb: float = _DEFAULT_CHUNK_MB,
    max_num_pages: int | None = _DEFAULT_CHUNK_MAX_PAGES,
) -> list[bytes]:
    """Splits a PDF into chunks below both max_chunk_mb and max_num_pages.

    garbage=4 + deflate on every tobytes() call gives a clean, accurate size so
    shared resources and stale cross-references don't cause the size check to lie.
    A single page that already exceeds the size limit is kept as its own chunk (can't split further).
    """
    max_bytes = int(max_chunk_mb * 1024 * 1024)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[bytes] = []
    try:
        logger.info(
            f"Splitting {len(doc)}-page PDF into {max_chunk_mb} MB"
            + (f" / {max_num_pages}-page" if max_num_pages else "") + " chunks"
        )
        chunk_doc = fitz.open()
        for i in range(len(doc)):
            # Flush current chunk if the page limit would be exceeded by adding this page
            if max_num_pages is not None and len(chunk_doc) >= max_num_pages:
                chunks.append(chunk_doc.tobytes(**_TOBYTES_OPTS))
                logger.info(f"Chunk {len(chunks)} saved (page limit), starting at page {i + 1}")
                chunk_doc = fitz.open()

            chunk_doc.insert_pdf(doc, from_page=i, to_page=i)
            serialized = chunk_doc.tobytes(**_TOBYTES_OPTS)
            if len(serialized) > max_bytes:
                if len(chunk_doc) == 1:
                    # Single page already exceeds size limit — save as-is, nothing to split
                    logger.warning(
                        f"Page {i + 1} alone is {len(serialized) / 1024 / 1024:.1f} MB"
                        f", exceeds {max_chunk_mb} MB limit"
                    )
                    chunks.append(serialized)
                    chunk_doc = fitz.open()
                else:
                    chunk_doc.delete_page(-1)
                    chunks.append(chunk_doc.tobytes(**_TOBYTES_OPTS))
                    logger.info(f"Chunk {len(chunks)} saved (size limit), ended before page {i + 1}")
                    chunk_doc = fitz.open()
                    chunk_doc.insert_pdf(doc, from_page=i, to_page=i)
        if len(chunk_doc) > 0:
            chunks.append(chunk_doc.tobytes(**_TOBYTES_OPTS))
            logger.info(f"Chunk {len(chunks)} saved (final)")
    finally:
        doc.close()
    return chunks


def pdf_chunks_to_zip(
    pdf_bytes: bytes,
    max_chunk_mb: float = _DEFAULT_CHUNK_MB,
    max_num_pages: int | None = _DEFAULT_CHUNK_MAX_PAGES,
) -> bytes:
    """Splits the PDF into size-bounded chunks and returns them as a ZIP archive."""
    chunks = split_pdf_into_chunks(pdf_bytes, max_chunk_mb=max_chunk_mb, max_num_pages=max_num_pages)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, chunk in enumerate(chunks):
            zf.writestr(f"chunk_{i + 1:03d}.pdf", chunk)
    return buf.getvalue()


def pdf_pages_to_folder(pdf_bytes: bytes, output_dir: str, dpi: int = 150, jpeg_quality: int = 85) -> list[str]:
    """Renders every page as a JPEG and saves to output_dir. Returns list of saved paths."""
    os.makedirs(output_dir, exist_ok=True)
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    paths = []
    try:
        logger.info(f"Rendering {len(doc)} page(s) at {dpi} dpi, jpeg_quality={jpeg_quality} to {output_dir}")
        for i, page in enumerate(doc):
            pixmap = page.get_pixmap(matrix=matrix)
            if pixmap.alpha:
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            path = os.path.join(output_dir, f"page_{i + 1:04d}.jpg")
            pixmap.save(path, output="jpeg", jpg_quality=jpeg_quality)
            paths.append(path)
    finally:
        doc.close()
    return paths


def pdf_chunks_to_folder(
    pdf_bytes: bytes,
    output_dir: str,
    max_chunk_mb: float = _DEFAULT_CHUNK_MB,
    max_num_pages: int | None = _DEFAULT_CHUNK_MAX_PAGES,
) -> list[str]:
    """Splits PDF into chunks and saves to output_dir. Returns list of saved paths."""
    os.makedirs(output_dir, exist_ok=True)
    chunks = split_pdf_into_chunks(pdf_bytes, max_chunk_mb=max_chunk_mb, max_num_pages=max_num_pages)
    paths = []
    for i, chunk in enumerate(chunks):
        path = os.path.join(output_dir, f"chunk_{i + 1:03d}.pdf")
        with open(path, "wb") as f:
            f.write(chunk)
        paths.append(path)
    return paths


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
        try:
            installed = [lang for lang in pytesseract.get_languages() if lang in _ALLOWED_LANGS]
            _TESSERACT_LANGS = "+".join(installed) if installed else "eng"
            if not installed:
                logger.warning(f"No allowed languages found in tessdata (allowed={_ALLOWED_LANGS}), falling back to 'eng'")
        except Exception as e:
            _TESSERACT_LANGS = "eng"
            logger.warning(f"Could not query tesseract languages ({e}), falling back to 'eng'")
        logger.info(f"Tesseract languages loaded: {_TESSERACT_LANGS}")
    return _TESSERACT_LANGS


_TESSERACT_CONFIG = "--oem 1 --psm 3"


def ocr_pdf(pdf_bytes: bytes) -> bytes:
    """Runs Tesseract OCR on every page in parallel and returns a searchable PDF."""
    tesseract_lang = _get_all_langs()

    # Render with PyMuPDF (faster than poppler/pdf2image)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    logger.info(f"OCR: rendering {total} page(s) with PyMuPDF, lang={tesseract_lang!r}")
    logger.info(f"Using {ec.ocr_max_workers=}")
    dpi = ec.image_dpi
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        images.append(PIL_Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
    doc.close()

    # Prevent each tesseract subprocess from spawning its own thread pool —
    # with multiple workers this causes CPU contention and kills throughput.
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")

    page_results: list[bytes | None] = [None] * total

    def _ocr_page(idx: int, image) -> tuple[int, bytes]:
        try:
            result = pytesseract.image_to_pdf_or_hocr(
                image, lang=tesseract_lang, extension="pdf", config=_TESSERACT_CONFIG
            )
        except Exception as e:
            if tesseract_lang == "eng":
                raise
            logger.warning(f"OCR page {idx + 1} failed with lang={tesseract_lang!r} ({e}), retrying with 'eng'")
            result = pytesseract.image_to_pdf_or_hocr(
                image, lang="eng", extension="pdf", config=_TESSERACT_CONFIG
            )
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
