from decouple import config

credentials_json = config("GCS_CREDENTIALS")
log_file = config("LOG_FILE_PATH", "test.log")
translation_project = config("TRANSLATION_PROJECT", "clean-axiom-299913")
translation_location = config("TRANSLATION_LOACTION", "us-central1")
translation_service_creds = config("TRANSLATION_SERVICE_CREDS")
gcs_output_bucket = config("TRANSLATION_OUTPUT_BUCKET", "nroad-translation-documents")