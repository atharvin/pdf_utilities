import io
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from translation_service.translate_utils import translate_pdf_sync

app = FastAPI()


@app.post(
    "/translate-pdf",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def upload_pdf(file: UploadFile = File(...)):
    pdf_bytes = await file.read()  # read entire file as bytes
    output_bytes = translate_pdf_sync(pdf_bytes)
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=translated_{file.filename}"
        },
    )
