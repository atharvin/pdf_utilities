import io
import asyncio
from functools import partial
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
import translation_service.env_config as ec
from translation_service.translate_utils import translate_pdf_sync
from translation_service.pdf_utils import is_scanned_pdf, ocr_pdf, pdf_chunks_to_zip, pdf_pages_to_zip

app = FastAPI()


@app.post(
    "/translate-pdf",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def upload_pdf(file: UploadFile = File(...), input_language:str = ""):
    pdf_bytes = await file.read()
    loop = asyncio.get_event_loop()
    output_bytes = await loop.run_in_executor(None, partial(translate_pdf_sync, pdf_bytes, input_language))
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=translated_{file.filename}"
        },
    )


@app.post(
    "/process-pdf",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
async def process_pdf(file: UploadFile = File(...), scanned: bool | None = None):
    pdf_bytes = await file.read()
    loop = asyncio.get_event_loop()
    stem = file.filename.removesuffix(".pdf") if file.filename else "document"

    if scanned is None:
        scanned = await loop.run_in_executor(None, is_scanned_pdf, pdf_bytes)

    if scanned:
        zip_bytes = await loop.run_in_executor(None, partial(pdf_pages_to_zip, pdf_bytes, ec.image_dpi))
        filename = f"{stem}_pages.zip"
    else:
        zip_bytes = await loop.run_in_executor(None, pdf_chunks_to_zip, pdf_bytes)
        filename = f"{stem}_chunks.zip"

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post(
    "/ocr-pdf",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def ocr_pdf_endpoint(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    loop = asyncio.get_event_loop()
    output_bytes = await loop.run_in_executor(None, partial(ocr_pdf, pdf_bytes))
    stem = file.filename.removesuffix(".pdf") if file.filename else "document"
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={stem}_ocr.pdf"},
    )
