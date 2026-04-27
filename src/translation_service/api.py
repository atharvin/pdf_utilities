import io
import asyncio
from functools import partial
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from translation_service.translate_utils import translate_pdf_sync

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
