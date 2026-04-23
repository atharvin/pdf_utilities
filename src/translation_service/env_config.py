from decouple import config

log_file = config("LOG_FILE_PATH", "app.log")
translation_project = config("TRANSLATION_PROJECT", "clean-axiom-299913")
translation_location = config("TRANSLATION_LOACTION", "us-central1")
gcs_output_bucket = config("TRANSLATION_OUTPUT_BUCKET", "nroad-translation-documents")
translation_private_key = config("TRANSLATION_PRIVATE_KEY")
translation_private_key_id = config("TRANSLATION_PRIVATE_KEY_ID")
translation_email = config("TRANSLATION_EMAIL")
translation_client_id = config("TRANSLATION_CLIENT_ID")