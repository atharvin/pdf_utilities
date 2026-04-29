from decouple import config

log_file = config("LOG_FILE_PATH", "app.log")
translation_project = config("TRANSLATION_PROJECT", "clean-axiom-299913")
translation_location = config("TRANSLATION_LOACTION", "us-central1")
gcs_output_bucket = config("TRANSLATION_OUTPUT_BUCKET", "nroad-translation-documents")
translation_private_key = config("TRANSLATION_PRIVATE_KEY")
translation_private_key_id = config("TRANSLATION_PRIVATE_KEY_ID")
translation_email = config("TRANSLATION_EMAIL")
translation_client_id = config("TRANSLATION_CLIENT_ID")
text_threshold = config("TEXT_THRESHOLD", 10, cast=int)
pdf_chunk_size_mb = config("CHUNK_MB", 9.0, cast=float)
image_dpi=config("IMAGE_DPI", 150, cast = int)