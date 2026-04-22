import traceback
import fitz

import translation_service.env_config as ec
from translation_service.logger_utils import logger
from google.cloud import translate_v3 as translate
from google.oauth2 import service_account


def translate_text(
    text: str | bytes | list[str] = "",
    target_language: str = "en",
    source_language: str | None = None,
) -> dict:
    credentials = service_account.Credentials.from_service_account_file(
        ec.translation_service_creds
    )
    translate_client = translate.Client(credentials=credentials)

    if isinstance(text, bytes):
        text = [text.decode("utf-8")]

    if isinstance(text, str):
        text = [text]

    results = translate_client.translate(
        values=text, target_language=target_language, source_language=source_language
    )
    return results


def translate_pdf_sync(
    file_path: bytes,
    target_language: str = "en",
    source_language: str = None,
) -> str:
    """
    Translate a document by sending its bytes directly to the API.
    No GCS bucket needed. Returns path to the translated output file.
    """
    try:
        project = ec.translation_project
        location = ec.translation_location
        logger.info(f"Configuring translation client in {project=} at {location=}")
        credentials = service_account.Credentials.from_service_account_file(
            ec.translation_service_creds,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        client = translate.TranslationServiceClient(credentials=credentials)
        parent = f"projects/{project}/locations/{location}"
    except Exception as _:
        tb = " >> ".join(
            line.strip() for line in traceback.format_exc().splitlines() if line.strip()
        )
        logger.error(f"Error in configuring translation client: {tb}")

    try:
        src = fitz.open(stream=file_path, filetype="pdf")
        result_doc = fitz.open()
        total_pages = len(src)
        logger.info(f"Translating pdf with {total_pages=}")
    except Exception as _:
        tb = " >> ".join(
            line.strip() for line in traceback.format_exc().splitlines() if line.strip()
        )
        logger.error(f"Error in reading the input file: {tb}")
        raise

    for start in range(0, total_pages, 20):
        end = min(start + 20, total_pages)
        logger.info(f"Processing page nums {start}-{end - 1}")
        try:
            batch_doc = fitz.open()
            batch_doc.insert_pdf(src, from_page=start, to_page=end - 1)
            doc_bytes = batch_doc.tobytes()
            request = translate.TranslateDocumentRequest(
                parent=parent,
                source_language_code=source_language or "",  # "" = auto-detect
                target_language_code=target_language,
                document_input_config=translate.DocumentInputConfig(
                    content=doc_bytes,  # <-- bytes sent directly
                    mime_type="application/pdf",
                ),
                document_output_config=translate.DocumentOutputConfig(
                    mime_type="application/pdf",  # keep the same output format
                ),
            )
            response = client.translate_document(request=request)
            output_bytes = response.document_translation.byte_stream_outputs[0]
            processed_doc = fitz.open("pdf", output_bytes)
            result_doc.insert_pdf(processed_doc)
            batch_doc.close()
            processed_doc.close()
        except Exception as _:
            tb = " >> ".join(
                line.strip()
                for line in traceback.format_exc().splitlines()
                if line.strip()
            )
            logger.error(f"Error in processing page nums {start}-{end - 1}: {tb}")
            raise
    src.close()
    return result_doc.tobytes()
